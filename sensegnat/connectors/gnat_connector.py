from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from uuid import uuid4

from sensegnat.common.time_utils import utcnow
from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative

logger = logging.getLogger(__name__)

_TAXII_CONTENT_TYPE = "application/stix+json;version=2.1"
_TAXII_ACCEPT = "application/taxii+json;version=2.1"


@dataclass
class PushResult:
    """Summary of a TAXII bundle push operation."""

    pushed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class GNATConnector:
    """Publishes SenseGNAT findings and narratives into GNAT via TAXII 2.1.

    Converts findings to STIX 2.1 Indicator objects and narratives to STIX
    Note objects, then POSTs them as a STIX bundle to the GNAT TAXII
    collection endpoint.

    When base_url/api_key are omitted the connector operates in record-only
    mode: to_record() and narrative_to_record() return STIX dicts without
    making any network calls.

    Parameters
    ----------
    base_url : str
        Root URL of the GNAT server, e.g. "https://gnat.example.com".
    api_key : str
        Bearer token issued by the GNAT instance.
    workspace : str
        TAXII collection / workspace name (default: "gnat").
    tlp : str
        TLP marking applied to all produced STIX objects (default: "white").
    confidence : int
        STIX confidence score 0-100 (default: 75).
    timeout : int
        HTTP request timeout in seconds (default: 30).
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        workspace: str = "gnat",
        tlp: str = "white",
        confidence: int = 75,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._workspace = workspace
        self._tlp = tlp
        self._confidence = confidence
        self._timeout = timeout

    # ------------------------------------------------------------------
    # STIX serialization
    # ------------------------------------------------------------------

    def finding_to_stix(self, finding: Finding) -> dict:
        """Convert a Finding to a STIX 2.1 Indicator dict."""
        now = utcnow().isoformat()
        dst = finding.evidence.get("destination", "")
        pattern = (
            f"[ipv4-addr:value = '{dst}']"
            if dst
            else f"[x-sensegnat-subject:id = '{finding.subject_id}']"
        )
        return {
            "type": "indicator",
            "spec_version": "2.1",
            "id": f"indicator--{uuid4()}",
            "created": now,
            "modified": now,
            "name": f"sensegnat:{finding.finding_type}:{finding.subject_id}",
            "pattern": pattern,
            "pattern_type": "stix",
            "valid_from": finding.seen_at.isoformat(),
            "indicator_types": ["anomalous-activity"],
            "confidence": self._confidence,
            # GNAT telemetry standard properties
            "x_gnat_sensor_type": "ids_alert",
            "x_gnat_sensor_id": "sensegnat",
            "x_gnat_signature": finding.finding_type,
            "x_gnat_tags": [finding.subject_id],
            "x_gnat_tlp": self._tlp,
            # SenseGNAT-specific properties
            "x_sensegnat_finding_id": finding.finding_id,
            "x_sensegnat_score": finding.score,
            "x_sensegnat_severity": finding.severity,
            "x_sensegnat_summary": finding.summary,
            "x_sensegnat_evidence": finding.evidence,
            "x_sensegnat_subject_id": finding.subject_id,
        }

    def narrative_to_stix(self, narrative: Narrative) -> dict:
        """Convert a Narrative to a STIX 2.1 Note dict."""
        now = utcnow().isoformat()
        return {
            "type": "note",
            "spec_version": "2.1",
            "id": f"note--{uuid4()}",
            "created": now,
            "modified": now,
            "content": narrative.summary,
            "object_refs": [],
            "x_gnat_sensor_id": "sensegnat",
            "x_gnat_tlp": self._tlp,
            "x_sensegnat_subject_id": narrative.subject_id,
            "x_sensegnat_finding_count": narrative.finding_count,
            "x_sensegnat_severity": narrative.severity,
            "x_sensegnat_score": narrative.score,
            "x_sensegnat_finding_types": list(narrative.finding_types),
        }

    # ------------------------------------------------------------------
    # Push (TAXII 2.1 transport)
    # ------------------------------------------------------------------

    def push_findings(self, findings: list[Finding]) -> PushResult:
        """Push findings as STIX Indicator objects to the GNAT TAXII endpoint."""
        if not findings:
            return PushResult()
        return self._push_bundle([self.finding_to_stix(f) for f in findings])

    def push_narratives(self, narratives: list[Narrative]) -> PushResult:
        """Push narratives as STIX Note objects to the GNAT TAXII endpoint."""
        if not narratives:
            return PushResult()
        return self._push_bundle([self.narrative_to_stix(n) for n in narratives])

    def _push_bundle(self, objects: list[dict]) -> PushResult:
        if not self._base_url or not self._api_key:
            logger.warning("GNATConnector: no base_url/api_key configured — push skipped")
            return PushResult()
        url = (
            f"{self._base_url}/taxii2/roots/gnat/collections/"
            f"{self._workspace}/objects/"
        )
        bundle = {
            "type": "bundle",
            "id": f"bundle--{uuid4()}",
            "spec_version": "2.1",
            "objects": objects,
        }
        payload = json.dumps(bundle).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": _TAXII_CONTENT_TYPE,
                "Accept": _TAXII_ACCEPT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                logger.info(
                    "GNATConnector: pushed %d objects → HTTP %d",
                    len(objects),
                    resp.status,
                )
                return PushResult(pushed=len(objects))
        except urllib.error.HTTPError as exc:
            msg = f"HTTP {exc.code}: {exc.reason}"
            logger.error("GNATConnector: push failed — %s", msg)
            return PushResult(errors=[msg])
        except OSError as exc:
            msg = str(exc)
            logger.error("GNATConnector: push failed — %s", msg)
            return PushResult(errors=[msg])

    # ------------------------------------------------------------------
    # Backwards-compatible record-only methods (no HTTP transport)
    # ------------------------------------------------------------------

    def to_record(self, finding: Finding) -> dict:
        """Return the STIX Indicator dict for *finding* (no network call)."""
        return self.finding_to_stix(finding)

    def narrative_to_record(self, narrative: Narrative) -> dict:
        """Return the STIX Note dict for *narrative* (no network call)."""
        return self.narrative_to_stix(narrative)

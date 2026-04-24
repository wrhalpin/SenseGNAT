from __future__ import annotations

import dataclasses
from collections import defaultdict
from uuid import uuid4

from sensegnat.behavior.profiler import ProfileBuilder
from sensegnat.config.settings import SenseGNATSettings
from sensegnat.connectors.gnat_connector import GNATConnector
from sensegnat.detection.peer_deviation import PeerDeviationDetector
from sensegnat.detection.policy_violation import PolicyViolationDetector
from sensegnat.detection.rarity import RareDestinationDetector
from sensegnat.detection.time_window_drift import TimeWindowDriftDetector
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding
from sensegnat.narrative.builder import NarrativeBuilder
from sensegnat.policy.engine import PolicyEngine
from sensegnat.storage.json_store import JsonFindingStore, JsonProfileStore
from sensegnat.storage.memory import InMemoryFindingStore, InMemoryProfileStore


class SenseGNATService:
    def __init__(self, adapter: EventAdapter, settings: SenseGNATSettings | None = None) -> None:
        self.adapter = adapter
        self.profile_builder = ProfileBuilder()
        self.rare_detector = RareDestinationDetector()
        self.peer_detector = PeerDeviationDetector()
        self.policy_violation_detector = PolicyViolationDetector()
        self.drift_detector = TimeWindowDriftDetector()
        self.narrative_builder = NarrativeBuilder()
        if settings is not None:
            self.profile_store = JsonProfileStore(settings.storage.profile_store_path)
            self.finding_store = JsonFindingStore(settings.storage.finding_store_path)
            self.policy_engine: PolicyEngine | None = (
                PolicyEngine.from_yaml(settings.policy_path)
                if settings.policy_path is not None
                else None
            )
            inv = settings.investigation
            self._investigation_lookup_enabled = inv.lookup_enabled
            self.connector = GNATConnector(
                base_url=settings.gnat.base_url,
                api_key=settings.gnat.api_key,
                workspace=settings.gnat.workspace,
                tlp=settings.gnat.tlp,
                confidence=settings.gnat.confidence,
                timeout=settings.gnat.timeout,
                investigation_lookup_timeout_s=inv.lookup_timeout_s,
                investigation_lookup_cache_ttl_s=inv.lookup_cache_ttl_s,
            )
        else:
            self.profile_store = InMemoryProfileStore()
            self.finding_store = InMemoryFindingStore()
            self.policy_engine = None
            self._investigation_lookup_enabled = False
            self.connector = GNATConnector()

    def run_once(self) -> list[dict]:
        events = list(self.adapter.fetch_events())
        if not events:
            return []

        # Snapshot existing profiles before this run so all detectors see
        # the same pre-run baseline, regardless of processing order.
        subject_ids = {e.source_user or e.source_host for e in events}
        existing: dict[str, BehaviorProfile | None] = {
            sid: self.profile_store.get(sid) for sid in subject_ids
        }

        profiles = self.profile_builder.build(events, policy_engine=self.policy_engine)
        findings_by_subject: dict[str, list[Finding]] = defaultdict(list)
        events_by_subject: dict[str, list[NormalizedNetworkEvent]] = defaultdict(list)

        for event in events:
            events_by_subject[event.source_user or event.source_host].append(event)

        for event in events:
            subject_id = event.source_user or event.source_host
            existing_profile = existing[subject_id]
            new_profile = profiles.get(subject_id)

            # Rarity: novel destination vs. historical profile
            finding = self.rare_detector.detect(event, existing_profile)
            if finding is not None:
                findings_by_subject[subject_id].append(finding)

            # Peer deviation: diverges from current-batch peer group behaviour
            if new_profile is not None:
                peer_group = new_profile.peer_group
                peer_profiles = [
                    p for sid, p in profiles.items()
                    if sid != subject_id and p.peer_group == peer_group and peer_group is not None
                ]
                finding = self.peer_detector.detect(event, new_profile, peer_profiles or None)
                if finding is not None:
                    findings_by_subject[subject_id].append(finding)

            # Policy violation: destination or port outside explicit allow-list
            finding = self.policy_violation_detector.detect(event, self.policy_engine)
            if finding is not None:
                findings_by_subject[subject_id].append(finding)

        # Time-window drift: per-subject after all events are seen
        for subject_id, subject_events in events_by_subject.items():
            finding = self.drift_detector.detect(subject_id, subject_events, existing[subject_id])
            if finding is not None:
                findings_by_subject[subject_id].append(finding)

        # Path B enrichment — feature-flagged; degrades gracefully on GNAT error
        if self._investigation_lookup_enabled:
            findings_by_subject = self._enrich_with_investigation_context(
                findings_by_subject, events_by_subject
            )

        # Serialize, persist, and collect published STIX objects
        run_id = str(uuid4())[:8]
        published: list[dict] = []
        stix_ids_by_investigation: dict[str, list[str]] = defaultdict(list)

        for subject_id, subject_findings in findings_by_subject.items():
            for finding in subject_findings:
                self.finding_store.add(finding)
                stix = self.connector.finding_to_stix(finding)
                published.append(stix)
                if finding.investigation_id:
                    stix_ids_by_investigation[finding.investigation_id].append(stix["id"])

        # Roll findings up into per-subject narratives
        for subject_id, subject_findings in findings_by_subject.items():
            narrative = self.narrative_builder.build(subject_id, subject_findings)
            if narrative is not None:
                stix = self.connector.narrative_to_stix(narrative)
                published.append(stix)
                if narrative.investigation_id:
                    stix_ids_by_investigation[narrative.investigation_id].append(stix["id"])

        # One Grouping per distinct investigation_id; untagged findings are left bare
        for investigation_id, obj_refs in stix_ids_by_investigation.items():
            published.append(self.connector.make_grouping(investigation_id, obj_refs, run_id))

        self.profile_store.put_many(profiles)
        return published

    def _enrich_with_investigation_context(
        self,
        findings_by_subject: dict[str, list[Finding]],
        events_by_subject: dict[str, list[NormalizedNetworkEvent]],
    ) -> dict[str, list[Finding]]:
        """Path B: attach investigation context to findings that don't already have it.

        Priority order per finding:
          1. Path A (policy rule already stamped it) — leave untouched.
          2. Telemetry hint (_gnat_investigation_hint on the Kafka record) — use directly.
          3. GNAT API lookup (GET /api/investigations?subject=...) — use first result.
          4. No match — leave unstamped (path C).

        Never blocks: GNAT errors degrade to path C, never raise.
        """
        enriched: dict[str, list[Finding]] = {}
        for subject_id, findings in findings_by_subject.items():
            hint = next(
                (e.investigation_hint for e in events_by_subject.get(subject_id, [])
                 if e.investigation_hint),
                None,
            )
            new_findings: list[Finding] = []
            for finding in findings:
                if finding.investigation_id:
                    # Path A — already stamped by a policy rule
                    new_findings.append(finding)
                elif hint:
                    # Telemetry hint short-circuits the API call
                    new_findings.append(dataclasses.replace(
                        finding,
                        investigation_id=hint,
                        investigation_link_type="inferred",
                    ))
                else:
                    try:
                        inv_ids = self.connector.find_investigations_for_subject(subject_id)
                    except Exception:
                        inv_ids = []
                    if inv_ids:
                        new_findings.append(dataclasses.replace(
                            finding,
                            investigation_id=inv_ids[0],
                            investigation_link_type="inferred",
                        ))
                    else:
                        new_findings.append(finding)
            enriched[subject_id] = new_findings
        return enriched

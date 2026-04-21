from __future__ import annotations

from collections import defaultdict

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
        else:
            self.profile_store = InMemoryProfileStore()
            self.finding_store = InMemoryFindingStore()
            self.policy_engine = None
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
        published: list[dict] = []
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
                self.finding_store.add(finding)
                published.append(self.connector.to_record(finding))
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
                    self.finding_store.add(finding)
                    published.append(self.connector.to_record(finding))
                    findings_by_subject[subject_id].append(finding)

            # Policy violation: destination or port outside explicit allow-list
            finding = self.policy_violation_detector.detect(event, self.policy_engine)
            if finding is not None:
                self.finding_store.add(finding)
                published.append(self.connector.to_record(finding))
                findings_by_subject[subject_id].append(finding)

        # Time-window drift: per-subject after all events are seen
        for subject_id, subject_events in events_by_subject.items():
            finding = self.drift_detector.detect(subject_id, subject_events, existing[subject_id])
            if finding is not None:
                self.finding_store.add(finding)
                published.append(self.connector.to_record(finding))
                findings_by_subject[subject_id].append(finding)

        # Roll findings up into per-subject narratives
        for subject_id, subject_findings in findings_by_subject.items():
            narrative = self.narrative_builder.build(subject_id, subject_findings)
            if narrative is not None:
                published.append(self.connector.narrative_to_record(narrative))

        self.profile_store.put_many(profiles)
        return published

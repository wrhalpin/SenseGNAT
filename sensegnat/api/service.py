from __future__ import annotations

from sensegnat.behavior.profiler import ProfileBuilder
from sensegnat.config.settings import SenseGNATSettings
from sensegnat.connectors.gnat_connector import GNATConnector
from sensegnat.detection.peer_deviation import PeerDeviationDetector
from sensegnat.detection.rarity import RareDestinationDetector
from sensegnat.ingestion.base import EventAdapter
from sensegnat.policy.engine import PolicyEngine
from sensegnat.storage.json_store import JsonFindingStore, JsonProfileStore
from sensegnat.storage.memory import InMemoryFindingStore, InMemoryProfileStore


class SenseGNATService:
    def __init__(self, adapter: EventAdapter, settings: SenseGNATSettings | None = None) -> None:
        self.adapter = adapter
        self.profile_builder = ProfileBuilder()
        self.rare_detector = RareDestinationDetector()
        self.peer_detector = PeerDeviationDetector()
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
        profiles = self.profile_builder.build(events, policy_engine=self.policy_engine)
        published: list[dict] = []

        for event in events:
            subject_id = event.source_user or event.source_host
            existing_profile = self.profile_store.get(subject_id)
            new_profile = profiles.get(subject_id)

            # Rarity: check against historical profile so first-contact still fires
            finding = self.rare_detector.detect(event, existing_profile)
            if finding is not None:
                self.finding_store.add(finding)
                published.append(self.connector.to_record(finding))

            # Peer deviation: compare against current-batch peers in the same group
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

        self.profile_store.put_many(profiles)
        return published

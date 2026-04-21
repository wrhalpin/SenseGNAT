from __future__ import annotations

from sensegnat.behavior.profiler import ProfileBuilder
from sensegnat.connectors.gnat_connector import GNATConnector
from sensegnat.detection.rarity import RareDestinationDetector
from sensegnat.ingestion.base import EventAdapter
from sensegnat.storage.memory import InMemoryFindingStore, InMemoryProfileStore


class SenseGNATService:
    def __init__(self, adapter: EventAdapter) -> None:
        self.adapter = adapter
        self.profile_builder = ProfileBuilder()
        self.detector = RareDestinationDetector()
        self.profile_store = InMemoryProfileStore()
        self.finding_store = InMemoryFindingStore()
        self.connector = GNATConnector()

    def run_once(self) -> list[dict]:
        events = list(self.adapter.fetch_events())
        profiles = self.profile_builder.build(events)
        published: list[dict] = []

        for event in events:
            subject_id = event.source_user or event.source_host
            existing_profile = self.profile_store.get(subject_id)
            finding = self.detector.detect(event, existing_profile)
            if finding is not None:
                self.finding_store.add(finding)
                published.append(self.connector.to_record(finding))

        self.profile_store.put_many(profiles)
        return published

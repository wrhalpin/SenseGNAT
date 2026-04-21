from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from sensegnat.models.events import NormalizedNetworkEvent


class EventAdapter(ABC):
    """Base adapter contract for telemetry sources."""

    @abstractmethod
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        raise NotImplementedError

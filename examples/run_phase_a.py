from __future__ import annotations

import logging
from pathlib import Path

from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.ingestion.sample_adapter import SampleEventAdapter

_CONFIG = Path(__file__).parent / "sensegnat.example.yaml"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings(_CONFIG)
    service = SenseGNATService(adapter=SampleEventAdapter(), settings=settings)
    published = service.run_once()
    logging.getLogger(__name__).info("published_records=%d", len(published))


if __name__ == "__main__":
    main()

from pathlib import Path

from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.ingestion.sample_adapter import SampleEventAdapter

_CONFIG = Path(__file__).parent / "sensegnat.example.yaml"


def main() -> None:
    settings = load_settings(_CONFIG)
    service = SenseGNATService(adapter=SampleEventAdapter(), settings=settings)
    published = service.run_once()
    print({"published_records": published})


if __name__ == "__main__":
    main()

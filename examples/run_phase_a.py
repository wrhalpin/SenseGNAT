from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.sample_adapter import SampleEventAdapter


def main() -> None:
    service = SenseGNATService(adapter=SampleEventAdapter())
    published = service.run_once()
    print({"published_records": published})


if __name__ == "__main__":
    main()

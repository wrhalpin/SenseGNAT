from __future__ import annotations

from sensegnat.config.settings import AdapterSettings
from sensegnat.ingestion.base import EventAdapter
from sensegnat.ingestion.csv_adapter import CsvEventAdapter
from sensegnat.ingestion.gnat_telemetry_adapter import GNATTelemetryAdapter
from sensegnat.ingestion.sample_adapter import SampleEventAdapter
from sensegnat.ingestion.splunk_adapter import SplunkEventAdapter
from sensegnat.ingestion.suricata_eve_adapter import SuricataEveAdapter
from sensegnat.ingestion.zeek_conn_adapter import ZeekConnLogAdapter

_ADAPTER_TYPES = ("sample", "csv", "zeek", "suricata", "gnat_telemetry", "splunk")


def build_adapter(settings: AdapterSettings) -> EventAdapter:
    """Build the EventAdapter described by an ``adapter:`` config section.

    Raises ValueError on an unknown type or a missing required field, so
    config mistakes surface at startup rather than mid-run.
    """
    adapter_type = settings.type.lower().strip()

    if adapter_type == "sample":
        return SampleEventAdapter()

    if adapter_type in ("csv", "zeek", "suricata"):
        if settings.path is None:
            raise ValueError(f"adapter type '{adapter_type}' requires 'path'")
        if adapter_type == "csv":
            return CsvEventAdapter(settings.path)
        if adapter_type == "zeek":
            return ZeekConnLogAdapter(settings.path)
        return SuricataEveAdapter(settings.path)

    if adapter_type == "gnat_telemetry":
        return GNATTelemetryAdapter(
            topic=settings.topic,
            brokers=settings.brokers,
            group_id=settings.group_id,
            max_messages=settings.max_messages,
        )

    if adapter_type == "splunk":
        if not settings.spl_query:
            raise ValueError("adapter type 'splunk' requires 'spl_query'")
        if not settings.host:
            raise ValueError("adapter type 'splunk' requires 'host'")
        return SplunkEventAdapter(
            spl_query=settings.spl_query,
            host=settings.host,
            port=settings.port,
            token=settings.token,
            username=settings.username,
            password=settings.password,
            earliest_time=settings.earliest_time,
            latest_time=settings.latest_time,
            max_results=settings.max_messages,
        )

    raise ValueError(
        f"unknown adapter type '{settings.type}' — expected one of {', '.join(_ADAPTER_TYPES)}"
    )

from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.config.settings import AdapterSettings
from sensegnat.ingestion.csv_adapter import CsvEventAdapter
from sensegnat.ingestion.factory import build_adapter
from sensegnat.ingestion.gnat_telemetry_adapter import GNATTelemetryAdapter
from sensegnat.ingestion.sample_adapter import SampleEventAdapter
from sensegnat.ingestion.splunk_adapter import SplunkEventAdapter
from sensegnat.ingestion.suricata_eve_adapter import SuricataEveAdapter
from sensegnat.ingestion.zeek_conn_adapter import ZeekConnLogAdapter


class TestBuildAdapter:
    def test_sample(self) -> None:
        adapter = build_adapter(AdapterSettings(type="sample"))
        assert isinstance(adapter, SampleEventAdapter)

    def test_default_type_is_sample(self) -> None:
        adapter = build_adapter(AdapterSettings())
        assert isinstance(adapter, SampleEventAdapter)

    def test_csv(self) -> None:
        adapter = build_adapter(AdapterSettings(type="csv", path=Path("events.csv")))
        assert isinstance(adapter, CsvEventAdapter)

    def test_zeek(self) -> None:
        adapter = build_adapter(AdapterSettings(type="zeek", path=Path("conn.log")))
        assert isinstance(adapter, ZeekConnLogAdapter)

    def test_suricata(self) -> None:
        adapter = build_adapter(AdapterSettings(type="suricata", path=Path("eve.json")))
        assert isinstance(adapter, SuricataEveAdapter)

    def test_gnat_telemetry(self) -> None:
        adapter = build_adapter(
            AdapterSettings(type="gnat_telemetry", topic="gnat.custom", brokers=["k1:9092"])
        )
        assert isinstance(adapter, GNATTelemetryAdapter)

    def test_splunk(self) -> None:
        adapter = build_adapter(
            AdapterSettings(
                type="splunk",
                spl_query="search index=network",
                host="splunk.test",
                token="tok",
            )
        )
        assert isinstance(adapter, SplunkEventAdapter)

    def test_type_is_case_insensitive(self) -> None:
        adapter = build_adapter(AdapterSettings(type="Sample"))
        assert isinstance(adapter, SampleEventAdapter)


class TestBuildAdapterErrors:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown adapter type 'netcat'"):
            build_adapter(AdapterSettings(type="netcat"))

    @pytest.mark.parametrize("adapter_type", ["csv", "zeek", "suricata"])
    def test_file_adapter_without_path_raises(self, adapter_type: str) -> None:
        with pytest.raises(ValueError, match=f"'{adapter_type}' requires 'path'"):
            build_adapter(AdapterSettings(type=adapter_type))

    def test_splunk_without_query_raises(self) -> None:
        with pytest.raises(ValueError, match="requires 'spl_query'"):
            build_adapter(AdapterSettings(type="splunk", host="splunk.test"))

    def test_splunk_without_host_raises(self) -> None:
        with pytest.raises(ValueError, match="requires 'host'"):
            build_adapter(AdapterSettings(type="splunk", spl_query="search *"))

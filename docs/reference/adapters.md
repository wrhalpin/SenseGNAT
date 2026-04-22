# Adapters Reference

All event adapters live in `sensegnat/ingestion/`. They implement the `EventAdapter` ABC and produce `NormalizedNetworkEvent` instances from a telemetry source.

---

## EventAdapter (ABC)

**Module:** `sensegnat/ingestion/base.py`

The abstract base class all adapters must subclass.

```python
class EventAdapter(ABC):
    @abstractmethod
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        raise NotImplementedError
```

### Contract

- `fetch_events()` must return an `Iterable[NormalizedNetworkEvent]`.
- It may be a list, a generator, or any other iterable.
- The caller (e.g., `SenseGNATService`) iterates the result exactly once.
- Implementations must not raise on missing optional fields; they must substitute defaults instead.

### Implementing a new adapter

1. Subclass `EventAdapter`.
2. Implement `fetch_events() -> Iterable[NormalizedNetworkEvent]`.
3. Map source fields to `NormalizedNetworkEvent` fields. See field rules below.

**Field rules shared by all adapters:**

| Target field | Rule |
|---|---|
| `event_id` | Use source-native ID if available; otherwise `str(uuid4())`. |
| `seen_at` | Must be timezone-aware. Attach `timezone.utc` to naive datetimes. |
| `source_user` | `None` if the source carries no user identity. |
| `protocol` | Lowercased before construction. |
| `bytes_out` / `bytes_in` | `0` when not available or unset in the source. |

---

## SampleEventAdapter

**Module:** `sensegnat/ingestion/sample_adapter.py`

Returns a hardcoded list of fixture events. No constructor arguments.

```python
class SampleEventAdapter(EventAdapter):
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]: ...
```

### Constructor

```python
SampleEventAdapter()
```

No parameters.

### Behavior

Returns a single hardcoded `NormalizedNetworkEvent`:

| Field | Value |
|---|---|
| `event_id` | `"evt-001"` |
| `seen_at` | `datetime.now(timezone.utc)` (computed at call time) |
| `source_host` | `"host-1"` |
| `source_user` | `"alice"` |
| `destination` | `"198.51.100.44"` |
| `destination_port` | `443` |
| `protocol` | `"tcp"` |
| `bytes_out` | `1048576` |
| `bytes_in` | `2201` |

### Use cases

- Development and smoke-testing of the pipeline.
- Unit tests that need a minimal event without reading files.

---

## CsvEventAdapter

**Module:** `sensegnat/ingestion/csv_adapter.py`

Reads `NormalizedNetworkEvent` records from a CSV file with named columns.

```python
class CsvEventAdapter(EventAdapter):
    def __init__(self, path: Path) -> None: ...
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]: ...
```

### Constructor

```python
CsvEventAdapter(path: Path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | `Path` | Path to the CSV file. |

### Column specification

| Column | Required | Type in CSV | Notes |
|---|---|---|---|
| `event_id` | No | string | UUID generated if absent or empty. |
| `seen_at` | Yes | string | ISO 8601 string or Unix epoch float. See parsing rules below. |
| `source_host` | Yes | string | |
| `source_user` | No | string | `None` when absent or empty. |
| `destination` | Yes | string | |
| `destination_port` | Yes | integer string | |
| `protocol` | Yes | string | Lowercased on parse. |
| `bytes_out` | No | integer string | `0` when absent or empty. |
| `bytes_in` | No | integer string | `0` when absent or empty. |

### `seen_at` parsing

```
1. Try datetime.fromisoformat(value) → attach timezone.utc
2. On ValueError, try datetime.fromtimestamp(float(value), tz=timezone.utc)
```

Both ISO 8601 strings (e.g., `"2024-01-15T12:34:56"`, `"2024-01-15T12:34:56+00:00"`) and Unix epoch floats (e.g., `"1705318496.0"`) are accepted.

### Notes

- Leading/trailing whitespace is stripped from all string fields.
- The CSV must have a header row. Column order does not matter; columns are accessed by name.
- `protocol` is always lowercased after parsing.
- If `source_user` is present in the header but the cell value is empty, `source_user` is set to `None`.

### Example CSV

```csv
event_id,seen_at,source_host,source_user,destination,destination_port,protocol,bytes_out,bytes_in
evt-001,2024-01-15T12:00:00,host-1,alice,198.51.100.10,443,tcp,1024,512
evt-002,2024-01-15T12:01:00,host-2,,10.0.0.1,22,tcp,200,800
evt-003,1705318496.0,host-3,bob,203.0.113.5,80,tcp,0,0
```

---

## ZeekConnLogAdapter

**Module:** `sensegnat/ingestion/zeek_conn_adapter.py`

Reads `NormalizedNetworkEvent` records from a Zeek `conn.log` file in TSV format.

```python
class ZeekConnLogAdapter(EventAdapter):
    def __init__(self, path: Path) -> None: ...
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]: ...
```

### Constructor

```python
ZeekConnLogAdapter(path: Path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | `Path` | Path to the Zeek `conn.log` file. |

### File format

Zeek `conn.log` is tab-separated. Lines beginning with `#` are comments or header metadata. The `#fields` line defines the column names and their order; column positions are **not hardcoded**.

```
#separator \x09
#set_separator ,
#empty_field (empty)
#unset_field -
#fields	ts	uid	id.orig_h	id.orig_p	id.resp_h	id.resp_p	proto	...
#types	time	string	addr	port	addr	port	enum	...
1705318496.123	CXWfTh...	192.168.1.5	54321	198.51.100.10	443	tcp	...
```

### Field mapping

| Zeek field | NormalizedNetworkEvent field | Notes |
|---|---|---|
| `uid` | `event_id` | UUID generated if absent or empty. |
| `ts` | `seen_at` | Unix epoch float → timezone-aware datetime. |
| `id.orig_h` | `source_host` | Falls back to `"unknown"` if absent. |
| `id.resp_h` | `destination` | |
| `id.resp_p` | `destination_port` | |
| `proto` | `protocol` | Lowercased. |
| `orig_bytes` | `bytes_out` | `0` when unset (`-`) or `(empty)`. |
| `resp_bytes` | `bytes_in` | `0` when unset (`-`) or `(empty)`. |

`source_user` is always `None`. Zeek `conn.log` carries no user identity.

### Skipped rows

A row is skipped (returns `None` from `_parse_row`) if any of the following are true:

- `ts` is unset (`-`) or `(empty)`.
- `id.resp_h` is unset (`-`) or `(empty)`.
- `id.resp_p` is unset (`-`) or `(empty)`.
- `ts` or `id.resp_p` cannot be parsed as a numeric value.

All `#` lines are skipped except the `#fields` line. Empty lines are skipped.

### Unset value handling

Zeek represents unset fields as `-` and empty fields as `(empty)`. Both are treated as absent. For `orig_bytes` and `resp_bytes`, absent values become `0`.

### Notes

- The adapter reads the `#fields` line dynamically, so it handles `conn.log` files with different column sets (e.g., files with or without `orig_bytes`).
- The adapter does not require the `#fields` line to appear before data rows, but data rows before `#fields` are silently skipped (no field mapping is available).

---

## SuricataEveAdapter

**Module:** `sensegnat/ingestion/suricata_eve_adapter.py`

Reads `NormalizedNetworkEvent` records from a Suricata EVE JSON file (newline-delimited JSON).

```python
class SuricataEveAdapter(EventAdapter):
    def __init__(self, path: Path) -> None: ...
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]: ...
```

### Constructor

```python
SuricataEveAdapter(path: Path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | `Path` | Path to the Suricata EVE JSON file. |

### File format

EVE JSON is one JSON object per line:

```json
{"timestamp":"2024-01-15T12:00:00.123456+0000","flow_id":1234567890,"event_type":"flow","src_ip":"192.168.1.5","dest_ip":"198.51.100.10","dest_port":443,"proto":"TCP","flow":{"bytes_toserver":1024,"bytes_toclient":512}}
{"timestamp":"2024-01-15T12:00:01.000000+0000","event_type":"dns","src_ip":"..."}
```

### Processed event types

Only records with `event_type` of `"flow"` or `"alert"` are processed. All other types (`"dns"`, `"http"`, `"stats"`, `"tls"`, etc.) are silently skipped.

### Field mapping

| EVE JSON field | NormalizedNetworkEvent field | Notes |
|---|---|---|
| `flow_id` | `event_id` | Converted to string. UUID generated if absent. |
| `timestamp` | `seen_at` | See timestamp parsing below. |
| `src_ip` | `source_host` | |
| `dest_ip` | `destination` | |
| `dest_port` | `destination_port` | |
| `proto` | `protocol` | Lowercased. |
| `flow.bytes_toserver` | `bytes_out` | `0` if `flow` key absent or value null. |
| `flow.bytes_toclient` | `bytes_in` | `0` if `flow` key absent or value null. |

`source_user` is always `None`. EVE flow/alert records carry no user identity.

### Timestamp parsing

Suricata EVE timestamps use the format `"2024-01-15T12:00:00.123456+0000"` — a bare UTC offset without a colon. Python's `fromisoformat` requires `+00:00`. The adapter normalises the offset before parsing:

```
"+0000" → "+00:00"
"-0500" → "-05:00"
```

If the parsed datetime is naive after conversion, `timezone.utc` is attached.

### Skipped records

A record is skipped if any of the following are true:

- `event_type` is not `"flow"` or `"alert"`.
- `src_ip`, `dest_ip`, `dest_port`, or `timestamp` is absent or empty.
- `dest_port` cannot be parsed as an integer.
- `timestamp` cannot be parsed as a datetime.
- The line is blank.
- The line contains invalid JSON.

Invalid lines are skipped silently (no exception is raised to the caller).

### Notes

- `flow` bytes fields are read from the nested `flow` object, not the top-level record. Alert records without a `flow` key produce `bytes_out=0`, `bytes_in=0`.

---

## GNATTelemetryAdapter

**Module:** `sensegnat/ingestion/gnat_telemetry_adapter.py`

Consumes live sensor telemetry from the Kafka topic shared with GNAT. Taps the same raw event stream that GNAT's `KafkaSourceReader` consumes, giving SenseGNAT access to the full network five-tuple before GNAT converts records to STIX.

**Requires:** `kafka-python-ng` (optional runtime dependency — `pip install kafka-python-ng`).

### Constructor

```python
GNATTelemetryAdapter(
    topic: str = "gnat.telemetry",
    brokers: list[str] | None = None,   # default: ["localhost:9092"]
    group_id: str = "sensegnat",
    max_messages: int | None = None,
    poll_timeout_ms: int = 5_000,
    sensor_types: frozenset[str] | None = None,
)
```

| Parameter | Default | Description |
|---|---|---|
| `topic` | `"gnat.telemetry"` | Kafka topic name |
| `brokers` | `["localhost:9092"]` | Broker address list |
| `group_id` | `"sensegnat"` | Consumer group for offset tracking |
| `max_messages` | `None` | Stop after N events; `None` drains until timeout |
| `poll_timeout_ms` | `5000` | Milliseconds to wait before declaring topic exhausted |
| `sensor_types` | `{"netflow", "ids_alert", "honeypot"}` | Accepted sensor_type values |

### Accepted sensor types

| `sensor_type` | Accepted | Reason |
|---|---|---|
| `netflow` | Yes | Full five-tuple available |
| `ids_alert` | Yes | Full five-tuple available |
| `honeypot` | Yes | Full five-tuple available |
| `dns_log` | No | No destination IP for profiling |
| `generic` | No | Fields not guaranteed |

### Field mapping

| Kafka field(s) | NormalizedNetworkEvent field | Notes |
|---|---|---|
| `src_ip` / `IPV4_SRC_ADDR` | `source_host` | NetFlow v9 name accepted |
| `dst_ip` / `IPV4_DST_ADDR` | `destination` | NetFlow v9 name accepted |
| `dst_port` / `L4_DST_PORT` / `dest_port` | `destination_port` | `0` when absent |
| `protocol` | `protocol` | Lowercased |
| `timestamp` / `_kafka_timestamp` | `seen_at` | ISO 8601 or epoch (ms or s) |
| `bytes_out` / `IN_BYTES` / `orig_bytes` | `bytes_out` | `0` when absent |
| `bytes_in` / `OUT_BYTES` / `resp_bytes` | `bytes_in` | `0` when absent |
| `tags[0]` | `source_user` | `None` when `tags` absent or empty |
| `flow_id` / `uid` / generated UUID | `event_id` | |

### Skip conditions

A record is silently skipped when:

- `sensor_type` is not in the accepted set.
- `src_ip` or `dst_ip` is absent or empty.

### Notes

- The consumer is always closed in a `finally` block, even when `max_messages` fires early.
- Epoch millisecond timestamps (Kafka's native format) are detected by value `> 1e10` and divided by 1 000 to produce seconds before conversion.
- `dest_port` is absent on some `alert` records that do not carry a full 5-tuple; such records are skipped.

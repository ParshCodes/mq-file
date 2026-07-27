# MQ File Processing Test Harness

> A QA-focused integration testing project for an enterprise-style file processing pipeline.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq&logoColor=white)
![Oracle](https://img.shields.io/badge/Oracle-Database_Free-F80000?logo=oracle&logoColor=white)
![Tests](https://img.shields.io/badge/pytest-9_tests_passing-0A9EDC?logo=pytest&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

## Why I built this

File-based integrations are still common in banking, insurance, healthcare, logistics, and other enterprise systems. Testing them involves more than checking whether one valid file reaches a database. A good QA strategy also asks:

- What happens when a file is malformed or valid in structure but wrong in meaning?
- Can messages disappear between the filesystem, queue, and database?
- Are duplicate deliveries safe?
- Can failed messages be investigated and replayed?
- Do logs and database records agree at the end of a run?

I built this project to demonstrate how I approach those questions. It combines an executable pipeline with a test harness, reconciliation SQL, structured log analysis, and an Excel reporting artifact.

## Project at a glance

```text
 incoming/              RabbitMQ                 Oracle Database
 XML / JSON  --->  orders queue  --->  consumer  --->  processed_orders
      |                    |            |
      |                    |            +-- inventory and tax logic
      |                    +----------------> dead-letter queue
      +-- schema failure -------------------> rejected/

                     Structured JSON logs
                              |
                   Python summary report
                              |
                       Excel VBA pivot
```

The producer validates order files and publishes valid messages to RabbitMQ. The consumer checks inventory, calculates tax, and saves the result in Oracle. Invalid files are rejected with a useful reason, while technical processing failures are routed to a dead-letter queue for investigation.

## What this project demonstrates

### Data quality and validation

- XML validation with an XSD
- JSON validation with JSON Schema Draft 2020-12
- Business-rule validation to confirm the declared total matches item quantity times unit price
- Safe XML parsing with external entities and network access disabled
- Clear rejection reasons for malformed and schema-invalid files

### Message queue and processing controls

- Durable RabbitMQ queues and persistent messages
- Mandatory routing and publisher confirmations
- Manual acknowledgements after successful database processing
- Dead-letter exchange and queue for technical failures
- Deterministic failure injection for repeatable tests, plus an optional 5% random failure rate
- Idempotent order processing to protect against duplicate MQ delivery

### Database and observability checks

- Transactional inventory updates using Oracle row locks
- Currency-safe tax calculation with round-half-up behavior
- Structured JSON Lines logs with timestamps, correlation IDs, stages, statuses, durations, and error details
- SQL reconciliation for sent, processed, and dead-lettered counts
- Queries that identify queued orders with no terminal outcome and database rows with no queue evidence
- Log reporting with failure root causes and p50, p95, and p99 processing times

## Automated test coverage

The current suite contains five focused unit tests and four live integration tests.

| Scenario | What the test proves |
|---|---|
| Valid XML and JSON | Both formats are normalized against their schemas |
| Invalid samples | Malformed JSON, invalid XML, and incorrect totals produce useful diagnostics |
| Known-good order | The message reaches Oracle with the expected subtotal, tax, and grand total |
| Malformed input | The file moves to `rejected/` and the root cause appears in the logs |
| Burst of 50 files | All 50 unique orders reach a terminal database state with no message loss |
| Forced processing failure | The order is not inserted and the original message reaches `orders.dead` |

Latest local run:

```text
Unit tests:        5 passed
Integration tests: 4 passed in 10.55s
```

The integration overlay disables random failures so the happy-path tests remain deterministic. Forced failures still exercise the real rejection and dead-letter path.

## Technology

| Area | Tools |
|---|---|
| Application | Python 3.11, `pika`, `lxml`, `jsonschema`, `python-oracledb` |
| Messaging | RabbitMQ 3.13 with management UI |
| Database | Oracle Database Free |
| Test automation | pytest, pytest-timeout |
| Infrastructure | Docker Compose |
| Reporting | JSON Lines, CSV, SQL, Excel VBA |

## Run it locally

### 1. Start the pipeline

Oracle needs more memory than a typical lightweight container. Allowing Docker about 4 GB is a practical starting point.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Local services:

| Service | Address | Credentials |
|---|---|---|
| RabbitMQ management | <http://localhost:15672> | `mq_user` / `mq_password` |
| RabbitMQ AMQP | `localhost:5672` | `mq_user` / `mq_password` |
| Oracle PDB | `localhost:1521/FREEPDB1` | `mq_user` / `mq_password` |

### 2. Set up Python 3.11

This project intentionally targets Python 3.11. Python 3.13 or 3.14 may try to compile pinned native packages instead of downloading compatible wheels.

```powershell
winget install Python.Python.3.11
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

### 3. Run the tests

Unit and schema tests:

```powershell
python -m pytest -m "not integration"
```

Live integration tests use an overlay that disables random failures but keeps forced DLQ testing enabled:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build producer consumer
python -m pytest -m integration -v
```

### 4. Try a sample order

The temporary-file rename models an atomic file drop, preventing the producer from reading a half-written file.

```powershell
Copy-Item sample_data/valid_order.json incoming/valid_order.tmp
Rename-Item incoming/valid_order.tmp valid_order.json
```

After processing:

- valid files move to `archive/`;
- invalid files move to `rejected/`;
- publish failures remain in `incoming/` for retry;
- pipeline events appear in `logs/pipeline.jsonl`.

## Investigating failures

### RabbitMQ

Open the management UI at <http://localhost:15672> and inspect:

- `orders` for messages waiting to be processed;
- `orders.dead` for failed messages;
- the `x-death` header for RabbitMQ routing history.

### Oracle reconciliation

Run [`sql/reconciliation.sql`](sql/reconciliation.sql) as `mq_user`. It reports:

1. sent, processed, and dead-lettered totals;
2. whether the totals reconcile;
3. queued orders with no terminal outcome;
4. processed rows with no matching queued event.

The consumer writes durable failure evidence before rejecting a message. If the audit write itself fails, the message is requeued instead of silently discarded.

### Logs and Excel reporting

Create an Excel-friendly summary:

```powershell
python tools/analyze_logs.py `
  --input logs/pipeline.jsonl `
  --output reports/log_summary.csv
```

The report contains stage/status counts, failed order IDs, root-cause categories, and processing-time percentiles.

To create the Excel view:

1. Open a macro-enabled workbook.
2. Press `Alt+F11` and import [`excel/ImportLogSummary.bas`](excel/ImportLogSummary.bas).
3. Save the workbook as `.xlsm`.
4. Run `ImportMQLogSummary` and select the generated CSV.

The macro builds a pivot summary by stage, status, and error type. The readable VBA source is committed instead of an opaque generated Office binary.

## How I would connect this to Splunk

The reporting code separates the log source from the summary logic. Today, `LocalJsonLinesSource` reads a local file. In production, I would add a `SplunkLogSource` that:

1. submits a search job to `/services/search/jobs`;
2. polls the search ID until the job completes;
3. pages through JSON results;
4. yields the same event fields used by the local adapter.

Authentication, TLS verification, time ranges, retries, and pagination would live in the Splunk adapter. The tested summary and CSV logic would remain unchanged. A sample SPL shape is documented in [`tools/analyze_logs.py`](tools/analyze_logs.py).

## Repository guide

```text
mq_harness/       Producer, consumer, validation, MQ, Oracle, and logging code
schemas/          XSD and JSON Schema definitions
sample_data/      Valid and intentionally invalid order files
tests/            Unit and live integration tests
sql/              Oracle schema setup and reconciliation queries
tools/            Pluggable structured-log analyzer
excel/            Importable VBA reporting macro
docker-compose.yml
```

## Design decisions and next steps

- **Recoverability over silent loss:** broker failures leave source files available for retry.
- **Deterministic tests:** forced failures test the DLQ without relying on random chance.
- **At-least-once safety:** the `order_id` primary key makes duplicate deliveries idempotent.
- **Reviewable evidence:** logs, SQL, test results, rejected files, and DLQ messages each provide a different audit trail.

If I extended the project, I would add concurrent inventory tests, consumer-restart/redelivery tests, larger performance runs with explicit latency SLAs, and an outbox/inbox pattern to reduce the transaction gap between Oracle and RabbitMQ.

## Safe cleanup

The following command stops the stack and deletes its Oracle and RabbitMQ test data volumes:

```powershell
docker compose down -v
```

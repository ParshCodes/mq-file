#!/usr/bin/env python3
"""Analyze a pluggable structured-log source and write an Excel-friendly CSV.

Production Splunk adaptation: implement LogSource.events() with a request such as
POST /services/search/jobs using a search like
`index=orders sourcetype=mq_harness | table timestamp order_id stage status error processing_ms`,
then page through /services/search/jobs/{sid}/results?output_mode=json. Authentication,
TLS verification, time bounds, retries and pagination belong in that adapter; the summary
logic below does not change.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Iterable


class LogSource(ABC):
    @abstractmethod
    def events(self) -> Iterable[dict]: ...


class LocalJsonLinesSource(LogSource):
    def __init__(self, path: Path):
        self.path = path

    def events(self):
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    yield {
                        "timestamp": "", "order_id": None, "stage": "log_parse",
                        "status": "failure", "error": f"line {line_number}: {exc}",
                    }


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percent
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return round(ordered[low], 3)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (rank - low), 3)


def summarize(events: Iterable[dict]) -> list[dict]:
    rows = list(events)
    counts = Counter((e.get("stage", "unknown"), e.get("status", "unknown")) for e in rows)
    output = [
        {"report_type": "COUNT", "stage": stage, "status": status, "order_id": "",
         "error_type": "", "error_detail": "", "metric": "event_count", "value": count}
        for (stage, status), count in sorted(counts.items())
    ]
    for event in rows:
        if event.get("status") in ("failure", "failed", "dead_lettered", "audit_failure"):
            detail = str(event.get("error", "unspecified error"))
            error_type = detail.split(":", 1)[0][:120]
            output.append({
                "report_type": "FAILURE", "stage": event.get("stage", ""),
                "status": event.get("status", ""), "order_id": event.get("order_id") or "UNKNOWN",
                "error_type": error_type, "error_detail": detail, "metric": "failure_count", "value": 1,
            })
    durations = [float(e["processing_ms"]) for e in rows if e.get("processing_ms") is not None]
    for label, p in (("processing_ms_p50", .50), ("processing_ms_p95", .95), ("processing_ms_p99", .99)):
        output.append({"report_type": "PERCENTILE", "stage": "processed", "status": "",
                       "order_id": "", "error_type": "", "error_detail": "",
                       "metric": label, "value": percentile(durations, p) or 0})
    return output


def main():
    parser = argparse.ArgumentParser(description="Summarize MQ harness JSONL logs")
    parser.add_argument("--input", type=Path, default=Path("logs/pipeline.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports/log_summary.csv"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = summarize(LocalJsonLinesSource(args.input).events())
    with args.output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["report_type", "stage", "status", "order_id", "error_type", "error_detail", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} summary rows to {args.output}")


if __name__ == "__main__":
    main()

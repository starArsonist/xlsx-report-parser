"""Serialise parsed data to JSON / CSV (long format: one line per device and day)."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable

from .models import DailyRecord, Report

CSV_FIELDS = [
    "serial_number", "device_id", "date", "consumption_kwh", "uptime_hours", "hashrate_ths",
]
_FIELD_BY_KIND = {
    "energy": "consumption_kwh",
    "uptime": "uptime_hours",
    "hashrate": "hashrate_ths",
}


def records_to_json(records: Iterable[DailyRecord]) -> str:
    return json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2) + "\n"


def records_to_csv(records: Iterable[DailyRecord]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({k: ("" if v is None else v) for k, v in record.to_dict().items()})
    return buffer.getvalue()


def report_to_records(report: Report) -> list[DailyRecord]:
    """Flatten a single report into daily records (only the report's own metric is set)."""
    field_name = _FIELD_BY_KIND[report.kind]
    records = []
    for row in report.rows:
        for day, value in row.values.items():
            if value is None:
                continue
            records.append(
                DailyRecord(
                    key=row.info.key,
                    serial_number=row.info.serial_number,
                    device_id=row.info.device_id,
                    day=day,
                    **{field_name: value},
                )
            )
    return records

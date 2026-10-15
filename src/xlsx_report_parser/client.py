"""Push parsed records to the hosting-billing-api bulk endpoints (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any

from .models import DailyRecord

TARGETS = {"stats": "/stats/bulk", "overrides": "/stats/overrides/bulk"}


class PushError(RuntimeError):
    """The API rejected a batch or could not be reached."""


def _batches(items: list[dict], size: int) -> Iterator[list[dict]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _item(record: DailyRecord, comment: str | None) -> dict[str, Any]:
    item: dict[str, Any] = {"date": record.day.isoformat()}
    if record.serial_number:
        item["serial_number"] = record.serial_number
    elif record.device_id:
        item["external_id"] = record.device_id
    for name in ("consumption_kwh", "uptime_hours", "hashrate_ths"):
        value = getattr(record, name)
        if value is not None:
            item[name] = value
    if comment:
        item["comment"] = comment
    return item


def push_records(
    base_url: str,
    records: Iterable[DailyRecord],
    *,
    target: str = "stats",
    api_key: str | None = None,
    comment: str | None = None,
    batch_size: int = 500,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST records in batches; returns aggregated counters from the API responses."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {sorted(TARGETS)}")
    url = base_url.rstrip("/") + TARGETS[target]
    items = [_item(r, comment if target == "overrides" else None) for r in records]

    summary: dict[str, Any] = {"sent": 0, "upserted": 0, "unknown_devices": []}
    for batch in _batches(items, batch_size):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        request = urllib.request.Request(
            url, data=json.dumps({"items": batch}).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise PushError(f"API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PushError(f"cannot reach {url}: {getattr(exc, 'reason', exc)}") from exc

        summary["sent"] += len(batch)
        summary["upserted"] += int(body.get("upserted", 0))
        for serial in body.get("unknown_devices", []):
            if serial not in summary["unknown_devices"]:
                summary["unknown_devices"].append(serial)
    return summary

"""Join energy / uptime / hashrate reports into one daily record per device and day."""

from __future__ import annotations

from datetime import date

from .models import DailyRecord, DeviceInfo, MergedResult, ParseWarning, Report

_FIELD_BY_KIND = {
    "energy": "consumption_kwh",
    "uptime": "uptime_hours",
    "hashrate": "hashrate_ths",
}


def merge_reports(*reports: Report) -> MergedResult:
    """Merge any combination of reports (at most one per kind).

    Devices are matched on serial number (falling back to device id). A device missing from
    one report still produces records for the metrics it does have; the mismatch is reported
    as a warning rather than silently filled with zeros.
    """
    kinds = [r.kind for r in reports]
    if len(set(kinds)) != len(kinds):
        raise ValueError("pass at most one report per kind")
    if not reports:
        raise ValueError("nothing to merge")

    warnings: list[ParseWarning] = [w for r in reports for w in r.warnings]
    devices: dict[str, DeviceInfo] = {}
    metrics: dict[tuple[str, date], dict[str, float | None]] = {}
    presence: dict[str, set[str]] = {}

    for report in reports:
        field_name = _FIELD_BY_KIND[report.kind]
        for row in report.rows:
            key = row.info.key
            presence.setdefault(key, set()).add(report.kind)
            if key in devices:
                devices[key].merge_missing(row.info)
            else:
                devices[key] = DeviceInfo(**{f: getattr(row.info, f) for f in vars(row.info)})
            for day, value in row.values.items():
                if value is not None:
                    metrics.setdefault((key, day), {})[field_name] = value

    for key, kinds_seen in sorted(presence.items()):
        missing = sorted({r.kind for r in reports} - kinds_seen)
        if missing:
            warnings.append(
                ParseWarning(None, f"device {key} is absent from the {', '.join(missing)} report")
            )

    records = [
        DailyRecord(
            key=key,
            serial_number=devices[key].serial_number,
            device_id=devices[key].device_id,
            day=day,
            **values,
        )
        for (key, day), values in sorted(metrics.items())
    ]
    return MergedResult(records=records, devices=devices, warnings=warnings)

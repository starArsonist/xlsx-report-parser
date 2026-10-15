"""Data structures produced by the parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class ReportFormatError(ValueError):
    """The workbook does not look like a supported report (no header, no date columns, ...)."""


@dataclass(frozen=True)
class ParseWarning:
    """A recoverable problem: the row/cell is skipped or blanked, parsing continues."""

    row: int | None
    message: str
    column: str | None = None

    def __str__(self) -> str:
        where = f"row {self.row}" if self.row is not None else "header"
        if self.column:
            where += f", column {self.column}"
        return f"{where}: {self.message}"


@dataclass
class DeviceInfo:
    """Static attributes of a device as found in the leading columns of a report."""

    device_id: str = ""
    serial_number: str = ""
    model: str = ""
    ip: str = ""
    mac: str = ""
    client: str = ""
    site: str = ""
    building: str = ""
    rack: str = ""
    shelf: str = ""
    slot: str = ""
    worker: str = ""
    comment: str = ""

    @property
    def key(self) -> str:
        """Stable identity used to join several reports: serial number first, then device id."""
        return (self.serial_number or self.device_id).strip().upper()

    def merge_missing(self, other: DeviceInfo) -> None:
        """Fill empty fields from ``other`` (used when joining reports)."""
        for name in self.__dataclass_fields__:
            if not getattr(self, name) and getattr(other, name):
                setattr(self, name, getattr(other, name))


@dataclass
class DeviceRow:
    info: DeviceInfo
    values: dict[date, float | None]
    row_number: int


@dataclass
class Report:
    kind: str
    unit: str
    dates: list[date]
    rows: list[DeviceRow]
    warnings: list[ParseWarning] = field(default_factory=list)
    sheet: str = ""


@dataclass(frozen=True)
class DailyRecord:
    """One device on one day, combining every metric that was available."""

    key: str
    serial_number: str
    device_id: str
    day: date
    consumption_kwh: float | None = None
    uptime_hours: float | None = None
    hashrate_ths: float | None = None

    def to_dict(self) -> dict:
        return {
            "serial_number": self.serial_number or None,
            "device_id": self.device_id or None,
            "date": self.day.isoformat(),
            "consumption_kwh": self.consumption_kwh,
            "uptime_hours": self.uptime_hours,
            "hashrate_ths": self.hashrate_ths,
        }


@dataclass
class MergedResult:
    records: list[DailyRecord]
    devices: dict[str, DeviceInfo]
    warnings: list[ParseWarning] = field(default_factory=list)

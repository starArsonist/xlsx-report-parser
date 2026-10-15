"""Parse wide XLSX device reports into clean daily records."""

from .merge import merge_reports
from .models import (
    DailyRecord,
    DeviceInfo,
    MergedResult,
    ParseWarning,
    Report,
    ReportFormatError,
)
from .parser import parse_report

__all__ = [
    "DailyRecord",
    "DeviceInfo",
    "MergedResult",
    "ParseWarning",
    "Report",
    "ReportFormatError",
    "merge_reports",
    "parse_report",
]

__version__ = "0.1.0"

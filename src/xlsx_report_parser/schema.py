"""Report kinds, units and header vocabulary (English and Russian aliases)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# ----------------------------------------------------------------------------- metrics


@dataclass(frozen=True)
class MetricSpec:
    kind: str
    target_unit: str
    default_unit: str
    factors: dict[str, float]  # normalised source unit -> multiplier into target_unit


METRICS: dict[str, MetricSpec] = {
    # Daily energy. Source files usually hold watt-hours; we always output kWh.
    "energy": MetricSpec(
        kind="energy",
        target_unit="kWh",
        default_unit="wh",
        factors={"wh": 0.001, "w": 0.001, "kwh": 1.0, "kw": 1.0, "mwh": 1000.0},
    ),
    # Hours the device was up during the day.
    "uptime": MetricSpec(
        kind="uptime",
        target_unit="h",
        default_unit="h",
        factors={"h": 1.0, "hours": 1.0, "ч": 1.0, "min": 1 / 60, "s": 1 / 3600},
    ),
    # Hash rate. Headers often carry the unit: "01.03.2026 (Th/s)". We normalise to TH/s.
    "hashrate": MetricSpec(
        kind="hashrate",
        target_unit="TH/s",
        default_unit="th/s",
        factors={"th/s": 1.0, "ph/s": 1000.0, "gh/s": 1e-3, "mh/s": 1e-6, "kh/s": 1e-9},
    ),
}


def normalise_unit(unit: str) -> str:
    return re.sub(r"\s+", "", unit.strip().casefold())


# ------------------------------------------------------------------------ base fields


def _norm(text: object) -> str:
    return re.sub(r"[\s_\-]+", " ", str(text).strip().casefold())


_ALIASES: dict[str, tuple[str, ...]] = {
    "device_id": ("id", "device id", "id устройства", "идентификатор"),
    "serial_number": ("sn", "serial", "serial number", "серийный номер", "серийник"),
    "model": ("model", "m", "модель"),
    "ip": ("ip", "ip address", "ip адрес"),
    "mac": ("mac", "mac address", "mac адрес"),
    "client": ("client", "c", "клиент"),
    "site": ("site", "hosting", "h", "площадка", "хостинг"),
    "building": ("building", "b", "контейнер", "здание"),
    "rack": ("rack", "r", "стойка"),
    "shelf": ("shelf", "s", "полка"),
    "slot": ("slot", "place", "p", "место"),
    "worker": ("worker", "воркер", "pool 1 worker"),
    "comment": ("comment", "com", "комментарий", "примечание"),
}

FIELD_BY_ALIAS: dict[str, str] = {
    _norm(alias): field for field, aliases in _ALIASES.items() for alias in aliases
}


def field_for_header(header: object) -> str | None:
    """Map a header cell to a ``DeviceInfo`` field name, or ``None`` if unknown."""
    if header is None:
        return None
    return FIELD_BY_ALIAS.get(_norm(header))


# ------------------------------------------------------------------------ date headers

_DMY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})(?:\s*\(([^)]*)\))?$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:\s*\(([^)]*)\))?$")


def parse_date_header(value: object) -> tuple[date, str | None] | None:
    """Recognise a date column header.

    Returns ``(day, unit)`` where ``unit`` is the normalised text in trailing parentheses
    (``"01.03.2026 (Th/s)"`` -> ``"th/s"``) or ``None``. Returns ``None`` for non-date headers.
    """
    if isinstance(value, datetime):
        return value.date(), None
    if isinstance(value, date):
        return value, None
    if not isinstance(value, str):
        return None

    text = value.strip()
    for pattern, order in ((_DMY, (3, 2, 1)), (_ISO, (1, 2, 3))):
        match = pattern.match(text)
        if match:
            y, m, d = (int(match.group(i)) for i in order)
            unit = match.group(4)
            try:
                return date(y, m, d), (normalise_unit(unit) if unit else None)
            except ValueError:
                return None
    return None

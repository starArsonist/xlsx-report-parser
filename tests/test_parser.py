import io
from datetime import date, datetime

import pytest
from helpers import make_workbook
from openpyxl import Workbook

from xlsx_report_parser import ReportFormatError, parse_report
from xlsx_report_parser.parser import coerce_number
from xlsx_report_parser.schema import parse_date_header

D1, D2 = date(2026, 3, 1), date(2026, 3, 2)


def test_energy_russian_headers_and_unit_conversion(tmp_path):
    path = make_workbook(
        tmp_path / "e.xlsx",
        [
            ["ID", "Серийный номер", "Клиент", "01.03.2026", "02.03.2026"],
            ["DEV-1", "SN-1", "Acme", 72000, 69500],
        ],
    )
    report = parse_report(path, "energy")
    assert report.unit == "kWh"
    assert report.dates == [D1, D2]
    row = report.rows[0]
    info = row.info
    assert (info.device_id, info.serial_number, info.client) == ("DEV-1", "SN-1", "Acme")
    assert row.values == {D1: 72.0, D2: 69.5}  # Wh -> kWh
    assert report.warnings == []


def test_energy_unit_override_and_header_suffix(tmp_path):
    path = make_workbook(
        tmp_path / "e.xlsx",
        [["SN", "01.03.2026", "02.03.2026 (MWh)"], ["SN-1", 72.5, 0.0695]],
    )
    # un-suffixed columns are kWh because of energy_unit; the suffixed one is converted
    report = parse_report(path, "energy", energy_unit="kwh")
    assert report.rows[0].values == {D1: 72.5, D2: 69.5}


def test_datetime_and_iso_header_cells(tmp_path):
    path = make_workbook(
        tmp_path / "u.xlsx",
        [["SN", datetime(2026, 3, 1), "2026-03-02"], ["SN-1", 23.5, 24]],
    )
    report = parse_report(path, "uptime")
    assert report.dates == [D1, D2]
    assert report.rows[0].values == {D1: 23.5, D2: 24.0}


def test_dates_are_sorted_even_if_columns_are_not(tmp_path):
    path = make_workbook(
        tmp_path / "u.xlsx", [["SN", "02.03.2026", "01.03.2026"], ["SN-1", 2, 1]]
    )
    report = parse_report(path, "uptime")
    assert report.dates == [D1, D2]
    assert report.rows[0].values == {D1: 1.0, D2: 2.0}


def test_hashrate_prefers_target_unit_in_either_column_order(tmp_path):
    th_first = make_workbook(
        tmp_path / "a.xlsx",
        [["SN", "01.03.2026 (Th/s)", "01.03.2026 (Mh/s)"], ["SN-1", 100.5, 100500000]],
    )
    mh_first = make_workbook(
        tmp_path / "b.xlsx",
        [["SN", "01.03.2026 (Mh/s)", "01.03.2026 (Th/s)"], ["SN-1", 100500000, 100.5]],
    )
    for path in (th_first, mh_first):
        report = parse_report(path, "hashrate")
        assert report.rows[0].values == {D1: 100.5}


def test_hashrate_converts_other_units_when_target_is_absent(tmp_path):
    path = make_workbook(
        tmp_path / "h.xlsx",
        [["SN", "01.03.2026 (Mh/s)", "02.03.2026 (Ph/s)"], ["SN-1", 2_000_000, 0.5]],
    )
    values = parse_report(path, "hashrate").rows[0].values
    assert values[D1] == pytest.approx(2.0)  # 2e6 Mh/s = 2 Th/s
    assert values[D2] == pytest.approx(500.0)


def test_unknown_unit_column_is_ignored_with_warning(tmp_path):
    path = make_workbook(
        tmp_path / "h.xlsx",
        [["SN", "01.03.2026 (Th/s)", "02.03.2026 (kg)"], ["SN-1", 100, 5]],
    )
    report = parse_report(path, "hashrate")
    assert report.dates == [D1]
    assert any("kg" in str(w) for w in report.warnings)


def test_messy_cells_become_none_with_precise_warnings(tmp_path):
    path = make_workbook(
        tmp_path / "e.xlsx",
        [
            ["SN", "01.03.2026", "02.03.2026", "03.03.2026", "04.03.2026", "05.03.2026"],
            ["SN-1", "12 345,5", "-", "oops", -5, None],
        ],
    )
    report = parse_report(path, "energy", energy_unit="kwh")
    values = report.rows[0].values
    assert values[D1] == 12345.5  # NBSP/space thousands separator and decimal comma
    assert all(values[date(2026, 3, d)] is None for d in (2, 3, 4, 5))
    messages = [str(w) for w in report.warnings]
    assert len(messages) == 2  # "-" and empty are silent; text and negative are reported
    assert any("oops" in m and "row 2" in m and "03.03.2026" in m for m in messages)
    assert any("negative" in m for m in messages)


def test_skips_empty_rows_rows_without_id_and_duplicates(tmp_path):
    path = make_workbook(
        tmp_path / "u.xlsx",
        [
            ["SN", "Model", "01.03.2026"],
            ["SN-1", "M1", 20],
            [None, None, None],
            [None, "ghost", 5],
            ["sn-1", "dup", 21],
            ["SN-2", "M2", 22],
        ],
    )
    report = parse_report(path, "uptime")
    assert [r.info.serial_number for r in report.rows] == ["SN-1", "SN-2"]
    assert [r.row_number for r in report.rows] == [2, 6]
    text = " | ".join(str(w) for w in report.warnings)
    assert "row 4" in text and "no serial number" in text
    assert "row 5" in text and "duplicate of row 2" in text


def test_numeric_ids_do_not_get_a_trailing_dot_zero(tmp_path):
    path = make_workbook(tmp_path / "u.xlsx", [["ID", "01.03.2026"], [1234.0, 20]])
    assert parse_report(path, "uptime").rows[0].info.device_id == "1234"


def test_accepts_file_objects_and_named_sheets(tmp_path):
    workbook = Workbook()
    workbook.active.title = "Cover"
    data = workbook.create_sheet("Data")
    data.append(["SN", "01.03.2026"])
    data.append(["SN-1", 20])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    report = parse_report(buffer, "uptime", sheet="Data")
    assert report.sheet == "Data"
    assert report.rows[0].values == {D1: 20.0}


def test_missing_sheet_raises_helpful_error(tmp_path):
    path = make_workbook(tmp_path / "u.xlsx", [["SN", "01.03.2026"], ["SN-1", 1]])
    with pytest.raises(ReportFormatError, match="Sheet1"):
        parse_report(path, "uptime", sheet="Nope")


def test_structural_errors(tmp_path):
    with pytest.raises(ReportFormatError, match="no date columns"):
        parse_report(make_workbook(tmp_path / "a.xlsx", [["SN", "Total"], ["SN-1", 5]]), "uptime")
    with pytest.raises(ReportFormatError, match="duplicate column"):
        parse_report(
            make_workbook(tmp_path / "b.xlsx", [["SN", "01.03.2026", "01.03.2026"], ["x", 1, 2]]),
            "uptime",
        )
    with pytest.raises(ReportFormatError, match="empty"):
        parse_report(make_workbook(tmp_path / "c.xlsx", []), "uptime")
    with pytest.raises(ValueError, match="unknown report kind"):
        parse_report(make_workbook(tmp_path / "d.xlsx", [["SN"]]), "weather")


def test_coerce_number_edge_cases():
    assert coerce_number(None) == (None, None)
    assert coerce_number("") == (None, None)
    assert coerce_number(True)[1] is not None
    assert coerce_number(float("nan"))[1] is not None
    assert coerce_number("1,5") == (1.5, None)
    assert coerce_number(0) == (0.0, None)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("01.03.2026", (D1, None)),
        (" 01.03.2026 (Th/s) ", (D1, "th/s")),
        ("2026-03-01", (D1, None)),
        ("2026-03-01 (kWh)", (D1, "kwh")),
        (datetime(2026, 3, 1, 13, 5), (D1, None)),
        (date(2026, 3, 1), (D1, None)),
        ("31.02.2026", None),
        ("Total", None),
        (None, None),
        (42, None),
    ],
)
def test_parse_date_header(value, expected):
    assert parse_date_header(value) == expected

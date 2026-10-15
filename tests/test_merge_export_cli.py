import contextlib
import csv
import io
import json
from datetime import date

import pytest
from helpers import FakeApi, make_workbook

from xlsx_report_parser import merge_reports, parse_report
from xlsx_report_parser.cli import main
from xlsx_report_parser.client import PushError, push_records
from xlsx_report_parser.export import records_to_csv, records_to_json
from xlsx_report_parser.sample import generate_sample

D1, D2 = date(2026, 3, 1), date(2026, 3, 2)


def three_reports(tmp_path):
    energy = make_workbook(
        tmp_path / "e.xlsx",
        [
            ["ID", "SN", "Клиент", "01.03.2026", "02.03.2026"],
            ["DEV-1", "SN-1", "Acme", 72000, 70000],
            ["DEV-2", "SN-2", "Beta", 60000, 61000],
        ],
    )
    uptime = make_workbook(
        tmp_path / "u.xlsx",
        [
            ["SN", "Model", "2026-03-01", "2026-03-02"],
            ["sn-1", "X-100", 24, 23.5],  # lower-case serial must still match SN-1
        ],
    )
    hashrate = make_workbook(
        tmp_path / "h.xlsx",
        [["SN", "01.03.2026 (Th/s)"], ["SN-1", 100.5], ["SN-3", 90]],
    )
    return (
        parse_report(energy, "energy"),
        parse_report(uptime, "uptime"),
        parse_report(hashrate, "hashrate"),
    )


def test_merge_joins_on_serial_case_insensitively(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    by_key = {(r.key, r.day): r for r in merged.records}

    full = by_key[("SN-1", D1)]
    assert (full.consumption_kwh, full.uptime_hours, full.hashrate_ths) == (72.0, 24.0, 100.5)
    assert by_key[("SN-1", D2)].hashrate_ths is None  # no hashrate column for that day
    assert by_key[("SN-2", D1)].uptime_hours is None  # SN-2 only exists in the energy report
    assert ("SN-3", D1) in by_key  # hashrate-only device still produces a record


def test_merge_combines_device_attributes_and_reports_mismatches(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    info = merged.devices["SN-1"]
    assert (info.client, info.model, info.device_id) == ("Acme", "X-100", "DEV-1")
    text = " | ".join(str(w) for w in merged.warnings)
    assert "SN-2 is absent from the hashrate, uptime report" in text
    assert "SN-3 is absent from the energy, uptime report" in text


def test_merge_records_are_sorted_and_skip_empty_days(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    keys = [(r.key, r.day) for r in merged.records]
    assert keys == sorted(keys)


def test_merge_argument_validation(tmp_path):
    energy, *_ = three_reports(tmp_path)
    with pytest.raises(ValueError, match="at most one"):
        merge_reports(energy, energy)
    with pytest.raises(ValueError, match="nothing to merge"):
        merge_reports()


def test_exports(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    data = json.loads(records_to_json(merged.records))
    assert data[0] == {
        "serial_number": "SN-1",
        "device_id": "DEV-1",
        "date": "2026-03-01",
        "consumption_kwh": 72.0,
        "uptime_hours": 24.0,
        "hashrate_ths": 100.5,
    }
    rows = list(csv.DictReader(io.StringIO(records_to_csv(merged.records))))
    assert rows[1]["hashrate_ths"] == ""  # None is an empty CSV cell, not "None"


# ------------------------------------------------------------------ sample files + CLI


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(args)
    return code, out.getvalue(), err.getvalue()


def test_generated_samples_round_trip(tmp_path):
    paths = generate_sample(tmp_path, days=7, devices=6, seed=1)
    assert [p.name for p in paths] == ["energy.xlsx", "uptime.xlsx", "hashrate.xlsx"]

    energy = parse_report(paths[0], "energy")
    uptime = parse_report(paths[1], "uptime")
    hashrate = parse_report(paths[2], "hashrate")
    assert len(energy.rows) == len(uptime.rows) == len(hashrate.rows) == 6
    assert len(energy.dates) == len(uptime.dates) == len(hashrate.dates) == 7
    assert not hashrate.warnings  # the Mh/s helper columns are resolved silently

    kwh = [v for r in energy.rows for v in r.values.values()]
    assert all(50 < v < 90 for v in kwh)  # ~3 kW * 24 h

    merged = merge_reports(energy, uptime, hashrate)
    assert len(merged.records) == 42
    gaps = [r for r in merged.records if r.uptime_hours is None]
    assert len(gaps) == 2  # one blank cell and one "-" placeholder in the uptime sample
    assert merged.warnings == []


def test_cli_sample_then_merge_to_csv(tmp_path):
    code, out, _ = run(["sample", str(tmp_path), "--days", "3", "--devices", "2"])
    assert code == 0 and out.count(".xlsx") == 3

    result = tmp_path / "daily.csv"
    code, _, err = run([
        "merge",
        "--energy", str(tmp_path / "energy.xlsx"),
        "--uptime", str(tmp_path / "uptime.xlsx"),
        "--hashrate", str(tmp_path / "hashrate.xlsx"),
        "-f", "csv", "-o", str(result),
    ])
    assert code == 0 and err == ""
    rows = list(csv.DictReader(result.open(encoding="utf-8")))
    assert len(rows) == 6 and rows[0]["serial_number"] == "SN-DEMO-0001"


def test_cli_parse_json_and_strict_mode(tmp_path):
    path = make_workbook(tmp_path / "u.xlsx", [["SN", "01.03.2026"], ["SN-1", "oops"]])
    code, out, err = run(["parse", str(path), "-k", "uptime"])
    assert code == 0 and json.loads(out) == []
    assert "oops" in err

    code, _, _ = run(["parse", str(path), "-k", "uptime", "--strict"])
    assert code == 1


def test_cli_errors_return_exit_code_2(tmp_path):
    code, _, err = run(["parse", str(tmp_path / "missing.xlsx"), "-k", "energy"])
    assert code == 2 and "error:" in err

    bad = make_workbook(tmp_path / "bad.xlsx", [["SN", "Total"], ["SN-1", 1]])
    code, _, err = run(["parse", str(bad), "-k", "energy"])
    assert code == 2 and "no date columns" in err

    code, _, err = run(["merge"])
    assert code == 2 and "at least one" in err


# ------------------------------------------------------------------------- push client


def test_push_sends_batches_with_api_key(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    with FakeApi() as api:
        summary = push_records(api.url, merged.records, api_key="k-123", batch_size=2)
    assert summary["sent"] == len(merged.records) == summary["upserted"]
    assert len(api.calls) == 3  # 5 records in batches of 2
    first = api.calls[0]
    assert first["path"] == "/stats/bulk" and first["api_key"] == "k-123"
    assert first["json"]["items"][0] == {
        "date": "2026-03-01",
        "serial_number": "SN-1",
        "consumption_kwh": 72.0,
        "uptime_hours": 24.0,
        "hashrate_ths": 100.5,
    }


def test_push_overrides_target_adds_comment_and_collects_unknown_devices(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    body = {"upserted": 1, "unknown_devices": ["SN-3"]}
    with FakeApi(body=body) as api:
        summary = push_records(
            api.url, merged.records, target="overrides", comment="March import", batch_size=100
        )
    assert api.calls[0]["path"] == "/stats/overrides/bulk"
    assert api.calls[0]["json"]["items"][0]["comment"] == "March import"
    assert summary["unknown_devices"] == ["SN-3"]


def test_push_errors_are_wrapped(tmp_path):
    merged = merge_reports(*three_reports(tmp_path))
    with FakeApi(status=500, body={"detail": "database down"}) as api:
        with pytest.raises(PushError, match="HTTP 500"):
            push_records(api.url, merged.records)
    with pytest.raises(PushError, match="cannot reach"):
        push_records("http://127.0.0.1:9", merged.records, timeout=1)


def test_cli_push_and_dry_run(tmp_path):
    generate_sample(tmp_path, days=2, devices=2)
    base = [
        "merge",
        "--energy", str(tmp_path / "energy.xlsx"),
        "--uptime", str(tmp_path / "uptime.xlsx"),
    ]
    with FakeApi() as api:
        code, out, err = run(base + ["--push", api.url, "--api-key", "secret"])
        assert code == 0 and out == ""  # nothing printed to stdout when pushing
        assert json.loads(err.strip().splitlines()[-1])["upserted"] == 4
        assert api.calls[0]["api_key"] == "secret"

        calls_before = len(api.calls)
        code, _, err = run(base + ["--push", api.url, "--dry-run"])
        assert code == 0 and "would send 4 records" in err
        assert len(api.calls) == calls_before

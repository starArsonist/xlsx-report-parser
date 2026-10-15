"""Command-line interface: parse / merge / sample."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .client import PushError, push_records
from .export import records_to_csv, records_to_json, report_to_records
from .merge import merge_reports
from .models import ParseWarning, ReportFormatError
from .parser import parse_report
from .sample import generate_sample


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xlsx-report", description="Parse wide XLSX device reports into daily records."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="parse a single report")
    p.add_argument("file")
    p.add_argument("-k", "--kind", required=True, choices=["energy", "uptime", "hashrate"])
    p.add_argument("--sheet")
    p.add_argument(
        "--energy-unit", choices=["wh", "kwh"], help="unit of un-suffixed energy columns"
    )
    p.add_argument("-f", "--format", choices=["json", "csv"], default="json")
    p.add_argument("-o", "--output")
    p.add_argument("--strict", action="store_true", help="exit with code 1 if there are warnings")

    m = sub.add_parser("merge", help="merge energy/uptime/hashrate reports")
    m.add_argument("--energy")
    m.add_argument("--uptime")
    m.add_argument("--hashrate")
    m.add_argument("--energy-unit", choices=["wh", "kwh"])
    m.add_argument("-f", "--format", choices=["json", "csv"], default="json")
    m.add_argument("-o", "--output")
    m.add_argument("--strict", action="store_true")
    m.add_argument("--push", metavar="URL", help="POST the records to a hosting-billing-api")
    m.add_argument("--target", choices=["stats", "overrides"], default="stats")
    m.add_argument("--api-key")
    m.add_argument("--comment", help="comment stored with overrides (--target overrides)")
    m.add_argument("--dry-run", action="store_true", help="with --push: show what would be sent")

    s = sub.add_parser("sample", help="write demo workbooks with fictional devices")
    s.add_argument("out_dir")
    s.add_argument("--start", type=date.fromisoformat, default=date(2026, 3, 1))
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--devices", type=int, default=6)
    s.add_argument("--seed", type=int, default=42)
    return parser


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _report_warnings(warnings: Sequence[ParseWarning]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample":
        for path in generate_sample(
            args.out_dir, start=args.start, days=args.days, devices=args.devices, seed=args.seed
        ):
            print(path)
        return 0

    try:
        if args.command == "parse":
            report = parse_report(
                args.file, args.kind, sheet=args.sheet, energy_unit=args.energy_unit
            )
            records, warnings = report_to_records(report), report.warnings
        else:
            inputs = (
                ("energy", args.energy),
                ("uptime", args.uptime),
                ("hashrate", args.hashrate),
            )
            reports = [
                parse_report(path, kind, energy_unit=args.energy_unit)
                for kind, path in inputs
                if path
            ]
            if not reports:
                print(
                    "error: pass at least one of --energy / --uptime / --hashrate",
                    file=sys.stderr,
                )
                return 2
            merged = merge_reports(*reports)
            records, warnings = merged.records, merged.warnings
    except (ReportFormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _report_warnings(warnings)

    problems = bool(warnings)
    if args.command == "merge" and args.push:
        if args.dry_run:
            print(f"dry run: would send {len(records)} records to {args.push}", file=sys.stderr)
        else:
            try:
                summary = push_records(
                    args.push,
                    records,
                    target=args.target,
                    api_key=args.api_key,
                    comment=args.comment,
                )
            except PushError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
            problems = problems or bool(summary["unknown_devices"])
    else:
        text = records_to_csv(records) if args.format == "csv" else records_to_json(records)
        _emit(text, args.output)

    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())

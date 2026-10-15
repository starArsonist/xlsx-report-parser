# xlsx-report-parser

Turn the "wide" XLSX reports that monitoring and billing systems love to export — **one row per
device, one column per day** — into clean, validated daily records you can load into a database
or push to an API.

```
ID        Serial number  Model  01.03.2026  02.03.2026  03.03.2026        serial_number  date        kwh     uptime  th/s
DEV-0001  SN-DEMO-0001   X-100  68958       70868       70472       ──▶   SN-DEMO-0001   2026-03-01  68.958  21.57   106.0
                                                                          SN-DEMO-0001   2026-03-02  70.868  22.0    103.34
```

Real exports are messy, and that is what this library is built for:

- **Header vocabulary in English and Russian** (`Серийный номер`, `SN`, `Serial number` → one field).
- **Date headers in several shapes**: `01.03.2026`, `2026-03-01`, real Excel dates, and with a
  unit suffix, e.g. `01.03.2026 (Th/s)`.
- **Unit conversion**: energy Wh/kWh/MWh → kWh, hash rate Ph/Th/Gh/Mh/s → TH/s, uptime
  h/min/s → hours. When a day has the same value in several units, the target unit wins.
- **Honest data**: empty cells stay `None` (a gap is not a zero). Text, negative numbers and
  NaN become `None` **plus a precise warning** (`row 7, column 03.03.2026: not a number: 'oops'`).
  Rows without an identity and duplicate devices are skipped with a warning, never silently.
- **Joining reports**: energy, uptime and hash-rate files are merged on serial number
  (case-insensitive, falling back to device id) into one record per device and day.
- **Optional push** to a [hosting-billing-api](https://github.com/starArsonist/hosting-billing-api)
  instance (stdlib `urllib`, batched, API-key header).

## Install

```bash
pip install .            # or: pip install -e ".[dev]"
```

Only dependency: `openpyxl`.

## Try it in 30 seconds

```bash
xlsx-report sample demo/                        # three workbooks with fictional devices
xlsx-report merge \
  --energy demo/energy.xlsx --uptime demo/uptime.xlsx --hashrate demo/hashrate.xlsx \
  -f csv
```

```csv
serial_number,device_id,date,consumption_kwh,uptime_hours,hashrate_ths
SN-DEMO-0001,DEV-0001,2026-03-01,68.958,21.57,106.0
SN-DEMO-0001,DEV-0001,2026-03-02,70.868,22.0,103.34
SN-DEMO-0002,DEV-0002,2026-03-03,70.701,,104.43
```

The sample files are in [`examples/`](examples/) — they deliberately mix Russian/English headers,
ISO and dotted dates, a telemetry gap, a `-` placeholder and extra `Mh/s` columns.

## CLI

```bash
xlsx-report parse report.xlsx --kind energy            # one report -> JSON
xlsx-report parse report.xlsx -k uptime --sheet Data -f csv -o uptime.csv
xlsx-report parse report.xlsx -k energy --energy-unit kwh --strict   # exit 1 on any warning

xlsx-report merge --energy e.xlsx --uptime u.xlsx -f json -o daily.json

# push straight into the API (use --dry-run first)
xlsx-report merge --energy e.xlsx --uptime u.xlsx --hashrate h.xlsx \
  --push http://localhost:8000 --api-key "$API_KEY" --target stats
xlsx-report merge --energy client_report.xlsx --push http://localhost:8000 \
  --target overrides --comment "Client report, March"
```

Exit codes: `0` success, `1` warnings with `--strict`, `2` unreadable/invalid input or API error.

## Library

```python
from xlsx_report_parser import merge_reports, parse_report

energy = parse_report("energy.xlsx", "energy")
uptime = parse_report("uptime.xlsx", "uptime")

for warning in energy.warnings + uptime.warnings:
    print(warning)                       # row 7, column 03.03.2026: not a number: 'oops'

merged = merge_reports(energy, uptime)
for record in merged.records:
    print(record.serial_number, record.day, record.consumption_kwh, record.uptime_hours)
```

## Design notes

- `parser.py` has one job: sheet → `Report`. It never reaches out to the network or the DB.
- Column selection happens once per date (`_select_date_columns`), so unit handling and
  duplicate detection live in one place instead of being repeated per report kind.
- `schema.py` is pure data (aliases, unit tables). Supporting a new vendor layout is usually a
  one-line alias addition, covered by a test.
- Reading is done in openpyxl's `read_only` mode and rows are materialised, so the workbook
  file handle is always closed.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite covers header detection, unit conversion, messy cell handling, row validation,
report joining, exports, the CLI and the HTTP push client (against an in-process fake API).

## License

MIT

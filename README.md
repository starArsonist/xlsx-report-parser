# xlsx-report-parser

Превращает «широкие» XLSX-отчёты, которые так любят выгружать системы мониторинга и биллинга —
**одна строка на устройство, один столбец на день** — в чистые проверенные посуточные записи,
которые можно загрузить в базу данных или отправить в API.

```
ID        Serial number  Model  01.03.2026  02.03.2026  03.03.2026        serial_number  date        kwh     uptime  th/s
DEV-0001  SN-DEMO-0001   X-100  68958       70868       70472       ──▶   SN-DEMO-0001   2026-03-01  68.958  21.57   106.0
                                                                          SN-DEMO-0001   2026-03-02  70.868  22.0    103.34
```

Реальные выгрузки неаккуратны, и библиотека создана именно для этого:

- **Заголовки на английском и русском** (`Серийный номер`, `SN`, `Serial number` → одно поле).
- **Заголовки с датами в разных форматах**: `01.03.2026`, `2026-03-01`, настоящие даты Excel и
  даты с единицей измерения в скобках, например `01.03.2026 (Th/s)`.
- **Преобразование единиц**: энергия Wh/kWh/MWh → кВт·ч, хешрейт Ph/Th/Gh/Mh/s → TH/s, аптайм
  h/min/s → часы. Если за один день значение есть сразу в нескольких единицах, побеждает целевая.
- **Честные данные**: пустые ячейки остаются `None` (пропуск — это не ноль). Текст,
  отрицательные числа и NaN превращаются в `None` **с точным предупреждением**
  (`row 7, column 03.03.2026: not a number: 'oops'`). Строки без идентификатора и дубликаты
  устройств пропускаются с предупреждением, а не молча.
- **Объединение отчётов**: файлы энергии, аптайма и хешрейта объединяются по серийному номеру
  (без учёта регистра, с запасным вариантом по id устройства) в одну запись на устройство и день.
- **Отправка в API (по желанию)** в экземпляр [hosting-billing-api](https://github.com/starArsonist/hosting-billing-api)
  (стандартный `urllib`, пакетами, ключ API в заголовке).

## Установка

Нужен [uv](https://docs.astral.sh/uv/).

```bash
uv sync                  # создаёт .venv и ставит проект вместе с группой dev
```

Единственная зависимость: `openpyxl`.

## Попробовать за 30 секунд

```bash
uv run xlsx-report merge \
  --energy examples/energy.xlsx --uptime examples/uptime.xlsx --hashrate examples/hashrate.xlsx \
  -f csv
```

```csv
serial_number,device_id,date,consumption_kwh,uptime_hours,hashrate_ths
SN-DEMO-0001,DEV-0001,2026-03-01,68.958,21.57,106.0
SN-DEMO-0001,DEV-0001,2026-03-02,70.868,22.0,103.34
...
SN-DEMO-0002,DEV-0002,2026-03-03,70.701,,104.43
```

Файлы из [`examples/`](examples/) намеренно смешивают русские и английские заголовки, даты в ISO
и с точками, пропуск в телеметрии, заглушку `-` и дополнительные столбцы `Mh/s`.

Сгенерировать собственные наборы с вымышленными устройствами (значения зависят от `--seed`,
поэтому отличаются от `examples/`):

```bash
uv run xlsx-report sample demo/
```

## CLI

```bash
uv run xlsx-report parse report.xlsx --kind energy            # один отчёт -> JSON
uv run xlsx-report parse report.xlsx -k uptime --sheet Data -f csv -o uptime.csv
uv run xlsx-report parse report.xlsx -k energy --energy-unit kwh --strict   # код 1 при любом предупреждении

uv run xlsx-report merge --energy e.xlsx --uptime u.xlsx -f json -o daily.json

# отправка прямо в API (сначала используйте --dry-run)
uv run xlsx-report merge --energy e.xlsx --uptime u.xlsx --hashrate h.xlsx \
  --push http://localhost:8000 --api-key "$API_KEY" --target stats
uv run xlsx-report merge --energy client_report.xlsx --push http://localhost:8000 \
  --target overrides --comment "Client report, March"
```

`--dry-run` работает только вместе с `--push`: ничего не отправляется, в stderr выводится
`dry run: would send N records to <URL>`.

Коды выхода: `0` — успех, `1` — предупреждения при `--strict`, `2` — нечитаемый или неверный
входной файл либо ошибка API.

## Библиотека

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

## Заметки по устройству

- У `parser.py` одна задача: лист → `Report`. Он никогда не обращается ни к сети, ни к БД.
- Столбцы выбираются один раз для каждой даты (`_select_date_columns`), поэтому обработка единиц
  и поиск дубликатов находятся в одном месте, а не повторяются для каждого вида отчёта.
- `schema.py` — чистые данные (синонимы, таблицы единиц). Поддержка нового формата вендора
  обычно сводится к добавлению одного синонима, который покрывается тестом.
- Чтение идёт в режиме `read_only` из openpyxl, строки материализуются, поэтому файловый
  дескриптор книги всегда закрывается.

## Тесты

```bash
uv sync
uv run ruff check .
uv run pytest
```

Набор тестов покрывает определение заголовков, преобразование единиц, обработку «грязных»
ячеек, проверку строк, объединение отчётов, экспорт, CLI и HTTP-клиент отправки (на встроенном
в процесс поддельном API).

## Лицензия

MIT

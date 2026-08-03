from __future__ import annotations

import csv
import io
import re
from typing import Any

from pydantic import ValidationError

from weather_to_docx.domain.models import Location

LOCATION_CSV_COLUMNS = (
    "id",
    "name",
    "latitude",
    "longitude",
    "elevation_m",
    "timezone",
    "group",
    "output_name",
)
LOCATION_CSV_REQUIRED = {"id", "name", "latitude", "longitude"}
MAX_LOCATION_CSV_BYTES = 2 * 1024 * 1024
MAX_LOCATION_CSV_ROWS = 1000

_LOCATION_CSV_ALIASES = {
    "id": "id",
    "identifier": "id",
    "ид": "id",
    "идентификатор": "id",
    "код": "id",
    "name": "name",
    "title": "name",
    "название": "name",
    "наименование": "name",
    "объект": "name",
    "latitude": "latitude",
    "lat": "latitude",
    "широта": "latitude",
    "longitude": "longitude",
    "lon": "longitude",
    "lng": "longitude",
    "долгота": "longitude",
    "elevation_m": "elevation_m",
    "elevation": "elevation_m",
    "height": "elevation_m",
    "высота": "elevation_m",
    "высота_м": "elevation_m",
    "высота_над_уровнем_моря": "elevation_m",
    "timezone": "timezone",
    "time_zone": "timezone",
    "часовой_пояс": "timezone",
    "group": "group",
    "группа": "group",
    "output_name": "output_name",
    "filename": "output_name",
    "имя_файла": "output_name",
    "имя_выходного_файла": "output_name",
}


def locations_to_csv(locations: list[Location]) -> str:
    """Сформировать UTF-8 CSV с BOM и разделителем ``;``.

    Такой файл без ручной настройки открывается в русской локали Microsoft
    Excel и LibreOffice Calc и при этом остаётся однозначным для обратного
    импорта.
    """

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(LOCATION_CSV_COLUMNS),
        delimiter=";",
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for location in locations:
        row = location.model_dump(mode="json")
        writer.writerow(
            {
                column: "" if row.get(column) is None else row.get(column)
                for column in LOCATION_CSV_COLUMNS
            }
        )
    return "\ufeff" + stream.getvalue()


def locations_from_csv(content: bytes | str) -> list[Location]:
    """Разобрать CSV координат с русскими или английскими заголовками.

    Поддерживаются разделители ``;``, ``,`` и табуляция, UTF-8 с BOM,
    необязательная первая строка ``sep=;`` и десятичная запятая.
    """

    if isinstance(content, str):
        raw = content.encode("utf-8")
    else:
        raw = content
    if not raw:
        raise ValueError("CSV-файл пуст")
    if len(raw) > MAX_LOCATION_CSV_BYTES:
        raise ValueError("CSV-файл превышает допустимый размер 2 МБ")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV должен быть сохранён в UTF-8") from exc

    lines = text.splitlines()
    declared_delimiter: str | None = None
    if lines and lines[0].strip().lower().startswith("sep="):
        declared_delimiter = lines[0].strip()[4:5] or None
        lines = lines[1:]
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("CSV-файл не содержит строк данных")

    dialect = _detect_dialect(text, declared_delimiter)
    try:
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    except csv.Error as exc:
        raise ValueError(f"Не удалось прочитать CSV: {exc}") from exc
    if not reader.fieldnames:
        raise ValueError("CSV не содержит строки заголовков")

    mapped_headers: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        normalized = _normalize_csv_header(raw_header)
        mapped = _LOCATION_CSV_ALIASES.get(normalized)
        if mapped:
            mapped_headers[raw_header] = mapped

    missing = LOCATION_CSV_REQUIRED - set(mapped_headers.values())
    if missing:
        raise ValueError(
            "CSV не содержит обязательные столбцы: " + ", ".join(sorted(missing))
        )

    result: list[Location] = []
    seen_ids: set[str] = set()
    try:
        for line_number, raw_row in enumerate(reader, start=2):
            if len(result) >= MAX_LOCATION_CSV_ROWS:
                raise ValueError(
                    f"CSV содержит больше {MAX_LOCATION_CSV_ROWS} координат"
                )
            if not any(str(value or "").strip() for value in raw_row.values()):
                continue

            row = {
                mapped_headers[header]: str(value or "").strip()
                for header, value in raw_row.items()
                if header in mapped_headers
            }
            try:
                payload: dict[str, Any] = {
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "latitude": _parse_csv_decimal(row.get("latitude"), "latitude"),
                    "longitude": _parse_csv_decimal(row.get("longitude"), "longitude"),
                    "elevation_m": (
                        _parse_csv_decimal(row.get("elevation_m"), "elevation_m")
                        if row.get("elevation_m")
                        else None
                    ),
                    "timezone": row.get("timezone") or "UTC",
                    "group": row.get("group") or None,
                    "output_name": row.get("output_name") or None,
                }
                location = Location.model_validate(payload)
            except (ValueError, ValidationError) as exc:
                raise ValueError(f"Ошибка в строке CSV {line_number}: {exc}") from exc
            if location.id in seen_ids:
                raise ValueError(
                    f"Ошибка в строке CSV {line_number}: повторяется идентификатор {location.id!r}"
                )
            seen_ids.add(location.id)
            result.append(location)
    except csv.Error as exc:
        raise ValueError(f"Ошибка структуры CSV: {exc}") from exc

    if not result:
        raise ValueError("CSV не содержит ни одной корректной координаты")
    return result


def _detect_dialect(text: str, declared_delimiter: str | None) -> type[csv.Dialect] | csv.Dialect:
    if declared_delimiter in {";", ",", "\t"}:
        class DeclaredDialect(csv.excel):
            delimiter = declared_delimiter

        return DeclaredDialect
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        class SemicolonDialect(csv.excel):
            delimiter = ";"

        return SemicolonDialect


def _normalize_csv_header(value: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "_", value.casefold()).strip("_")


def _parse_csv_decimal(value: str | None, field: str) -> float:
    if value is None or not value.strip():
        raise ValueError(f"не заполнено поле {field}")
    normalized = value.strip().replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"поле {field} не является числом: {value!r}") from exc

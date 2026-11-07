from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class ParsedList:
    columns: list[str]
    rows: list[dict[str, str]]
    row_keys: list[str | None]


_DATE_FORMATS = (
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%y %I:%M %p",
)
_TIME_FORMATS = ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M", "%I %p")
_MORE_SUFFIX = re.compile(r"(?:\s*More(?:\s*(?:\.{1,3}|…))?)+\s*$", re.IGNORECASE)
_UNSELECTED_OPTION_OPEN = r"<option\b(?![^>]*\sselected(?:\s|=|/?>))[^>]*>"
_UNSELECTED_OPTION_TEXT = re.compile(
    _UNSELECTED_OPTION_OPEN + r"(.*?)</option\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNSELECTED_OPTION_BYTES = re.compile(
    _UNSELECTED_OPTION_OPEN.encode("ascii") + rb"(.*?)</option\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNSELECTED_OPTION_RUN_TEXT = re.compile(
    rf"(?:{_UNSELECTED_OPTION_OPEN}.*?</option\s*>\s*)+",
    re.IGNORECASE | re.DOTALL,
)
_UNSELECTED_OPTION_RUN_BYTES = re.compile(
    rb"(?:<option\b(?![^>]*\sselected(?:\s|=|/?>))[^>]*>.*?</option\s*>\s*)+",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_space(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _collapse_unselected_options_text(match: re.Match[str]) -> str:
    return " ".join(
        option.group(1) for option in _UNSELECTED_OPTION_TEXT.finditer(match.group())
    )


def _collapse_unselected_options_bytes(match: re.Match[bytes]) -> bytes:
    return b" ".join(
        option.group(1) for option in _UNSELECTED_OPTION_BYTES.finditer(match.group())
    )


def strip_unselected_option_markup(html: str | bytes) -> str | bytes:
    if isinstance(html, bytes):
        return _UNSELECTED_OPTION_RUN_BYTES.sub(
            _collapse_unselected_options_bytes, html
        )
    return _UNSELECTED_OPTION_RUN_TEXT.sub(_collapse_unselected_options_text, html)


def strip_more_suffix(value: str | None) -> str | None:
    if value is None:
        return None
    return _MORE_SUFFIX.sub("", value).strip()


def _cell_text(cell: Tag) -> str:
    visible = _normalize_space(cell.get_text(" ", strip=True))
    candidates = [visible] if visible else []
    for element in [cell, *cell.find_all(True)]:
        for attribute in ("title", "alt", "data-title", "data-original-title"):
            value = element.get(attribute)
            if isinstance(value, str) and value.strip():
                candidates.append(_normalize_space(value))
    checkbox = cell.find("input", attrs={"type": "checkbox"})
    if checkbox is not None:
        candidates.append("checked" if checkbox.has_attr("checked") else "unchecked")
    for image in cell.find_all("img"):
        marker = " ".join(
            str(image.get(attribute, ""))
            for attribute in ("src", "alt", "title", "class")
        ).lower()
        if "unchecked" in marker or "uncheck" in marker:
            candidates.append("unchecked")
        elif any(token in marker for token in ("checked", "checkmark", "tick")):
            candidates.append("checked")
    if not candidates:
        return ""
    if "unchecked" in candidates:
        return "unchecked"
    if "checked" in candidates:
        return "checked"
    return max(candidates, key=len)


def _row_key(row: Tag) -> str | None:
    for anchor in row.find_all("a", href=True):
        query = parse_qs(urlparse(anchor["href"]).query)
        keys = query.get("editid1")
        if keys and keys[0]:
            return keys[0]
    return None


def _table_score(table: Tag) -> tuple[int, int, int, int, int]:
    rows = table.find_all("tr")
    row_keys = sum(_row_key(row) is not None for row in rows)
    data_rows = sum("rnr-row" in row.get("class", []) for row in rows)
    header = table.select_one("tr.rnr-toprow")
    header_cells = len(header.find_all(["th", "td"], recursive=False)) if header else 0
    is_grid = int("rnr-gridtable" in table.get("class", []))
    return row_keys, int(header is not None), data_rows, header_cells, is_grid


def parse_phprunner_list(html: str | bytes) -> ParsedList:
    soup = BeautifulSoup(strip_unselected_option_markup(html), "lxml")
    try:
        tables = soup.find_all("table")
        table = max(tables, key=_table_score, default=None)
        if table is None:
            return ParsedList([], [], [])
        header_row = table.select_one("tr.rnr-toprow")
        if header_row is None:
            header_row = next(
                (
                    row
                    for row in table.find_all("tr")
                    if row.find("th", recursive=False)
                ),
                None,
            )
        if header_row is None:
            return ParsedList([], [], [])

        header_cells = header_row.find_all(["th", "td"], recursive=False)
        headers: list[str | None] = []
        seen: dict[str, int] = {}
        for cell in header_cells:
            label = _normalize_space(cell.get_text(" ", strip=True))
            if not label:
                headers.append(None)
                continue
            seen[label] = seen.get(label, 0) + 1
            headers.append(label if seen[label] == 1 else f"{label} ({seen[label]})")

        columns = [header for header in headers if header]
        rows: list[dict[str, str]] = []
        row_keys: list[str | None] = []
        for row in table.find_all("tr"):
            if row is header_row:
                continue
            key = _row_key(row)
            if key is None and "rnr-row" not in row.get("class", []):
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            if len(cells) != len(headers):
                if len(cells) > len(headers):
                    cells = cells[-len(headers) :]
                else:
                    cells = [None] * (len(headers) - len(cells)) + cells
            parsed = {
                header: _cell_text(cell) if cell is not None else ""
                for header, cell in zip(headers, cells, strict=False)
                if header
            }
            rows.append(parsed)
            row_keys.append(key)
        return ParsedList(columns, rows, row_keys)
    finally:
        soup.decompose()


def parse_money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text_value = _normalize_space(value)
    if not text_value or text_value.lower() in {"n/a", "na", "none", "-", "—"}:
        return None
    negative = text_value.startswith("(") and text_value.endswith(")")
    text_value = text_value.strip("()").replace(",", "").replace("$", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text_value)
    if not match:
        return None
    try:
        result = Decimal(match.group())
    except InvalidOperation:
        return None
    return -abs(result) if negative else result


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text_value = _normalize_space(value)
    if not text_value or text_value.lower() in {"n/a", "na", "none", "-", "—"}:
        return None
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text_value, date_format).date()
        except ValueError:
            continue
    return None


def parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    text_value = _normalize_space(value).upper().replace(".", "")
    if not text_value or text_value.lower() in {"n/a", "na", "none", "-", "—"}:
        return None
    for time_format in _TIME_FORMATS:
        try:
            return datetime.strptime(text_value, time_format).time()
        except ValueError:
            continue
    return None


def parse_checkbox(value: str | Tag | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, Tag):
        inputs = value.find_all("input", attrs={"type": "checkbox"})
        if inputs:
            return any(item.has_attr("checked") for item in inputs)
        markers = " ".join(
            str(item.get(attribute, ""))
            for item in [value, *value.find_all(True)]
            for attribute in ("src", "alt", "title", "class")
        ).lower()
        if "unchecked" in markers or "unchecked" in value.get_text(" ", strip=True):
            return False
        if any(marker in markers for marker in ("checked", "checkmark", "tick")):
            return True
        text_value = _cell_text(value)
    else:
        text_value = _normalize_space(value)
    normalized = text_value.strip().lower()
    if normalized in {"1", "yes", "y", "true", "checked", "✓", "☑", "x"}:
        return True
    if normalized in {"0", "no", "n", "false", "unchecked", "✗", "☐", ""}:
        return False if normalized else None
    return None


def parse_local_datetime(
    date_value: str | None, time_value: str | None
) -> datetime | None:
    parsed_date = parse_date(date_value)
    if parsed_date is None:
        return None
    parsed_time = parse_time(time_value) or time.min
    return datetime.combine(parsed_date, parsed_time)


def parse_checkbox_cell(cell: Tag | None, text_value: str | None = None) -> bool | None:
    if cell is not None:
        return parse_checkbox(cell)
    return parse_checkbox(text_value)


def parse_first(row: dict[str, str], labels: tuple[str, ...]) -> str | None:
    for label in labels:
        value = row.get(label)
        if value is not None and value.strip():
            return value.strip()
    return None


def parse_row_key_or_order(row: dict[str, str], row_key: str | None) -> int | None:
    value = parse_first(
        row,
        ("Order #", "Order Number", "Order No.", "Order No", "Order # (2)"),
    )
    candidate = value or row_key
    if candidate is None:
        return None
    match = re.search(r"\d+", candidate.replace(",", ""))
    return int(match.group()) if match else None


def as_raw_strings(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value or "") for key, value in row.items()}

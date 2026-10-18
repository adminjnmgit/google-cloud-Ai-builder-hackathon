"""Report sources. Each loader returns ``(reports, skipped)``.

A report is a :class:`Report`; its ``type`` is the report section (Biz News, Share Market, Commodity ...).
"""

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Iterable
from datetime import datetime
from typing import IO, Any, TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..errors import SourceError


class Report(TypedDict):
    sl: int
    when: datetime
    date: str  # ``when`` as 'YYYY-MM-DD HH:MM', the shape the frontend uses
    type: str
    headline: str
    summary: str
    machine: bool  # the English text is an offline machine translation


_DATE_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d')
_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
TRANSLATIONS_TABLE = 'orbit_translations'


def parse_when(value: Any) -> datetime | None:
    """Parse the date shapes seen in the feed ('2026-10-16 9:40', '2026-10-16 13:47:00', ISO). None if unparseable."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    raw = str(value or '').strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=None)
    except ValueError:
        return None


def _report(
    sl: int | None,
    when_raw: Any,
    section: str | None,
    headline: str | None,
    summary: str | None,
    *,
    machine: bool = False,
) -> Report | None:
    """Build a Report, or None when the row has no usable serial number or date."""
    when = parse_when(when_raw)
    if when is None or sl is None:
        return None
    return Report(
        sl=int(sl),
        when=when,
        date=when.strftime('%Y-%m-%d %H:%M'),
        type=(section or '').strip(),
        headline=(headline or '').strip(),
        summary=(summary or '').strip(),
        machine=machine,
    )


def _collect(rows: Iterable[Report | None]) -> tuple[list[Report], int]:
    reports: list[Report] = []
    skipped = 0
    for report in rows:
        if report is None:
            skipped += 1
        else:
            reports.append(report)
    return reports, skipped


def _to_int(value: Any) -> int | None:
    raw = str(value or '').strip()
    return int(raw) if raw.isdigit() else None


# --------------------------------------------------------------------------- CSV


def reports_from_csv(handle: IO[str]) -> tuple[list[Report], int]:
    """Read a report sheet from an open text handle.

    Accepts the Jagran export (``#, Section, Headline, Summary, Date (IST), Type, URL, Translated Headline,
    Translated Summary``), where the English columns are used and untranslated rows are skipped, and the plain
    sheet (``Sl No, Type, Date, Headline, Summary``) whose text is already English.
    """
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    reader = csv.DictReader(handle)
    columns = {name.strip(): name for name in (reader.fieldnames or [])}

    def pick(*names: str) -> str | None:
        return next((columns[n] for n in names if n in columns), None)

    sl_col = pick('#', 'Sl No', 'sl', 'id')
    date_col = pick('Date (IST)', 'Date')
    translated_headline = pick('Translated Headline')
    translated_summary = pick('Translated Summary')
    headline_col = translated_headline or pick('Headline')
    summary_col = translated_summary or pick('Summary')
    type_col = pick('Section', 'Type')
    required = {'serial': sl_col, 'date': date_col, 'headline': headline_col, 'summary': summary_col}
    missing = [name for name, col in required.items() if col is None]
    if missing:
        raise SourceError(f'CSV is missing {", ".join(missing)} column(s); found {list(columns)}')

    def rows() -> Iterable[Report | None]:
        for row in reader:
            if translated_headline and not (row.get(translated_headline) or '').strip():
                continue  # not translated: outside the English feed, not an error
            yield _report(
                _to_int(row.get(sl_col)),
                row.get(date_col),
                row.get(type_col) if type_col else '',
                row.get(headline_col),
                row.get(summary_col),
            )

    return _collect(rows())


def reports_from_csv_path(path: str) -> tuple[list[Report], int]:
    try:
        with open(path, encoding='utf-8-sig', newline='') as handle:
            return reports_from_csv(handle)
    except OSError as error:
        raise SourceError(f'Cannot read {path}: {error.strerror or error}') from error


# --------------------------------------------------------------------------- MySQL table

# The newsroom table may have been created with another collation than ours; naming one explicitly keeps the
# comparison of its text with a translation from failing with "illegal mix of collations".
_COLLATION = 'COLLATE utf8mb4_unicode_ci'
# A row has "its own" English when the newsroom table's headline_en is filled in.
_OWN_ENGLISH = "(j.headline_en IS NOT NULL AND j.headline_en <> '')"
# A row is machine text when it has a translation row AND its own English is either empty or just a copy of
# that translation (`tools/translate_hindi.py apply` copies translations into the newsroom table).
_IS_MACHINE = (
    f'(t.biz_id IS NOT NULL AND (NOT {_OWN_ENGLISH} '
    f'OR (j.headline_en = t.headline_en {_COLLATION} AND j.summary_en = t.summary_en {_COLLATION})))'
)
_TABLE_QUERY = f"""
    SELECT COALESCE(j.source_no, j.id) AS sl, j.section, j.published_at,
           CASE WHEN {_OWN_ENGLISH} THEN j.headline_en ELSE t.headline_en END AS headline,
           CASE WHEN {_OWN_ENGLISH} THEN j.summary_en ELSE t.summary_en END AS summary,
           CASE WHEN {_IS_MACHINE} THEN 1 ELSE 0 END AS is_machine
    FROM `{{table}}` j LEFT JOIN {TRANSLATIONS_TABLE} t ON t.biz_id = j.id
    WHERE {{where}}
    ORDER BY j.id
"""
_WHERE_HUMAN_ONLY = f'{_OWN_ENGLISH} AND NOT {_IS_MACHINE}'
_WHERE_WITH_MACHINE = f'({_OWN_ENGLISH} OR t.biz_id IS NOT NULL)'


def reports_from_table(
    connection: Connection, table: str = 'jagran_biz', *, machine: bool = False
) -> tuple[list[Report], int]:
    """Read English reports from the MySQL table the newsroom export is loaded into.

    By default only articles with human (or LLM) English are read. With ``machine=True``, articles that have no
    English of their own but do have an offline machine translation (``orbit_translations``) are included too,
    flagged ``machine=True``. Human English always wins when both exist.
    """
    if not _IDENTIFIER.match(table):
        raise SourceError(f'Unsafe table name: {table!r}')
    query = _TABLE_QUERY.format(table=table, where=_WHERE_WITH_MACHINE if machine else _WHERE_HUMAN_ONLY)
    return _collect(
        _report(sl, published_at, section, headline, summary, machine=bool(is_machine))
        for sl, section, published_at, headline, summary, is_machine in connection.execute(text(query))
    )

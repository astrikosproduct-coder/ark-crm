"""
Export: a workbook a person can actually read, for a module with 80-100 fields.

One flat sheet of a hundred columns is unusable, and one sheet per STAGE splits
a record's identity away from its numbers. So the workbook follows the form:

    Summary          the list screen's columns — what most people want
    <one per section of the form>   Record ID + Name, then that section's fields
    Stage history    per-stage answers (a reason given at Stage 3) as rows
    <one per child list>            Record ID + Name, one line per child row

Every sheet opens with Record ID and Name, so the sheets join on either.
Headers are labels, values are labels and names, dates are real Excel dates.
The rows are exactly what the list screen shows under the same filter — the
export calls the module's own list endpoint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Stage
from .fields import Column, Directory, child_columns, display_value, extensions, register_columns, section_title
from .workbook import new_book, safe_sheet_title, save, write_table

STAGE_KEY = re.compile(r"^(?P<base>.+)__s(?P<stage>\d+)$")
SKIP_SECTIONS = {"__header"}
NOT_A_CELL = {"childlist", "file"}


@dataclass
class ExportTarget:
    key: str
    field_module: str
    list_view: str
    title: str
    name_field: str
    #: Returns the module's list rows for the request's own filters.
    rows: Callable[[], list[dict[str, Any]]]
    #: Child lists live under another module's sidecar key (payment_milestones is leads.*).
    child_module_of: dict[str, str] = field(default_factory=dict)


def export_workbook(db: Session, target: ExportTarget, generated: date | datetime) -> bytes:
    rows = target.rows()
    directory = Directory(db)
    columns = [c for c in register_columns(db, target.field_module)]
    by_api = {c.api_name: c for c in columns}
    book = new_book()
    book.properties.title = f"ARK CRM {target.title} export"
    taken: set[str] = set()
    banner = f"ARK CRM  ·  {target.title} export  ·  {generated:%d-%b-%Y}  ·  {len(rows):,} {'record' if len(rows) == 1 else 'records'}"

    def ident(row: dict[str, Any]) -> list[Any]:
        return [row.get("id"), row.get(target.name_field) or (row.get("__labels") or {}).get(target.name_field)]

    def cells(row: dict[str, Any], cols: list[Column]) -> list[Any]:
        labels = row.get("__labels") or {}
        return [display_value(c, row.get(c.api_name), directory, labels) for c in cols]

    # ---- Summary: the list screen's own columns
    view = extensions().get("list_views", {}).get(target.list_view) or {}
    summary_cols = [by_api[ref.split(".")[-1]] for ref in view.get("columns", []) if ref.split(".")[-1] in by_api]
    summary_cols = [c for c in summary_cols if c.api_name != target.name_field]
    sheet = book.create_sheet(safe_sheet_title("Summary", taken))
    write_table(
        sheet,
        ["Record ID", by_api[target.name_field].label if target.name_field in by_api else "Name", *[c.label for c in summary_cols]],
        [ident(r) + cells(r, summary_cols) for r in rows],
        ["text", "text", *[c.type for c in summary_cols]],
        banner=banner,
    )

    # ---- one sheet per section, in form order
    sections: dict[str, list[Column]] = {}
    for column in columns:
        if column.section in SKIP_SECTIONS or column.type in NOT_A_CELL or column.api_name == target.name_field:
            continue
        sections.setdefault(column.section, []).append(column)
    for section, section_cols in sections.items():
        sheet = book.create_sheet(safe_sheet_title(section_title(section), taken))
        write_table(
            sheet,
            ["Record ID", "Name", *[c.label for c in section_cols]],
            [ident(r) + cells(r, section_cols) for r in rows],
            ["text", "text", *[c.type for c in section_cols]],
            banner=banner,
        )

    # ---- per-stage answers
    stage_names = {s.stage: s.name for s in db.scalars(select(Stage))}
    history: list[list[Any]] = []
    for row in rows:
        for key in sorted(k for k in row if STAGE_KEY.match(k)):
            match = STAGE_KEY.match(key)
            base = by_api.get(match["base"])
            value = row.get(key)
            if base is None or value in (None, "", []):
                continue
            number = int(match["stage"])
            stage = f"{number} · {stage_names[number]}" if number in stage_names else str(number)
            history.append(ident(row) + [stage, base.label, display_value(base, value, directory)])
    if history:
        sheet = book.create_sheet(safe_sheet_title("Stage history", taken))
        write_table(sheet, ["Record ID", "Name", "Stage", "Field", "Value"], history, ["text", "text", "text", "text", "text"], banner=banner)

    # ---- child lists
    for column in columns:
        if column.type != "childlist":
            continue
        spec = child_columns(target.child_module_of.get(column.api_name, target.field_module), column.api_name)
        child_cols = spec[1] if spec else []
        lines: list[list[Any]] = []
        for row in rows:
            for child in row.get(column.api_name) or []:
                if not isinstance(child, dict):
                    continue
                if not child_cols:
                    child_cols = [Column(api_name=k, label=k.replace("_", " ").title(), type="text", section="") for k in child]
                lines.append(ident(row) + [display_value(c, child.get(c.api_name), directory) for c in child_cols])
        if lines:
            sheet = book.create_sheet(safe_sheet_title(column.label, taken))
            write_table(sheet, ["Record ID", "Name", *[c.label for c in child_cols]], lines, ["text", "text", *[c.type for c in child_cols]], banner=banner)

    book.active = 0
    return save(book)


def export_filename(title: str, today: date | datetime) -> str:
    return f"Astrikos ARK - {title} {today:%d-%b-%Y}.xlsx"

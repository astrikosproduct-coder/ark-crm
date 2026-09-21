"""
Import: map the columns, preview every row, then commit all of them or none.

EVERY ROW GOES THROUGH THE MODULE'S OWN CREATE ROUTE
-----------------------------------------------------
Not a bulk INSERT. `create_lead`, `create_account` and `create_contact` are
called exactly as FastAPI calls them, so an imported record gets the same id
allocation, the same duplicate-pursuit guard, the same stage pair, the same
audit entry and the same created_by stamp as one typed into the form. A rule
added to a route later applies to imports without anyone remembering to.

ALL OR NOTHING, WITH A REAL PREVIEW
-----------------------------------
The work runs on one connection inside one outer transaction; the session
joins it in "create_savepoint" mode, so each route's own `db.commit()` only
releases a SAVEPOINT and a refused row rolls back to its own savepoint. Rows
therefore see each other — two rows for the same End Client trip the
duplicate guard exactly as two saves would. At the end the OUTER transaction
is rolled back for a preview, or when any row failed; it is committed only
when every row passed.

WHAT A SAVE DEMANDS, AND NOT MORE
---------------------------------
A form save checks formats, lengths, choices and lookups — never Mandatory
fields, which bite at a stage move (src/lib/spec/validation.ts). An import
row is checked the same way, plus one thing a sheet needs that a form does
not: the record's name, so no nameless record is created.

LEADS: STAGE 0 ONLY
-------------------
Agreed as "Stage 0-1" on 17 Sep 2026, narrowed while building: a lead enters
Stage 1 through the move's blocking checks (X0.1, X0.2, E1.1, E1.2 — "client
agrees to a demo", "meeting scheduled"…), which a person confirms in the
Update Stage dialog. A spreadsheet cannot honestly confirm them, so an import
creates Stage 0 leads and the move to Stage 1 happens in ARK.

WHAT A PERSON TYPES, AND WHAT ARK DOES WITH IT (decided 17 Sep 2026)
--------------------------------------------------------------------
* A choice ARK doesn't recognise ("SI") is never guessed. The preview lists
  each such text once, with how many rows use it; the person picks the choice
  it means on the review screen, and the next check sends those `answers`.
* A name with no record in ARK is reported once per column with every name
  missing, so "import the Accounts first" is one sentence, not forty rows.
* A value in a column that doesn't apply to the row — Partner Tier on an End
  Client — is LEFT OUT with a warning, and the row still imports. It is only
  left out when every field the rule reads is on the sheet or has a known
  default; a rule ARK can't evaluate here never throws data away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..database import engine
from ..models import User
from .conditions import ConditionError, _tokens, evaluate
from .fields import (
    CellError,
    Column,
    Directory,
    MissingRecord,
    UnknownChoice,
    _noun,
    import_columns,
    is_blank,
    read_cell,
    read_checkbox,
)
from .workbook import (
    FileRefusal,
    choice_header,
    choice_key,
    condition_in_words,
    header_key,
    how_to_fill,
    is_guidance_row,
    trim_rows,
)

MAX_ROWS = 1000  # ~40 s through the create route; a larger file is split, not timed out
_NOT_A_STAGE = object()
MAX_REPORTED_ROWS = 200
HEADER_SEARCH_ROWS = 10
MAX_NAMES_REPORTED = 20


@dataclass
class ImportTarget:
    """What an import needs to know about one module."""

    key: str
    field_module: str
    title: str
    noun: str
    plural: str
    name_field: str
    schema: type
    #: (validated payload, session, user) -> the new record's id. Must apply
    #: every rule the module's POST route applies — see leads.insert_lead.
    create: Callable[[Any, Session, User], str]
    max_stage: int | None = None
    stage_field: str | None = None
    stage_picklist: str | None = None
    #: Extra per-row rule, e.g. a Partners import must name a partner type.
    row_rule: Callable[[dict[str, Any], Directory], str | None] | None = None
    #: Values every imported row starts from, before its own cells.
    defaults: dict[str, Any] = field(default_factory=dict)


@dataclass
class Slot:
    """What one spreadsheet column fills: a field, or one choice of a multi-choice field."""

    column: Column
    choice: str | None = None  # the choice's key, for an "Account Type · End Client" column
    choice_label: str | None = None


@dataclass
class Mapping:
    sheet: str
    header_index: int
    header_row: list[Any]
    #: column index -> what it fills, for every header that maps
    by_index: dict[int, Slot]
    unmapped: list[str]
    duplicates: list[str]


def columns_for(db: Session, target: ImportTarget) -> list[Column]:
    return import_columns(db, target.field_module, max_stage=target.max_stage)


def pick_sheet(target: ImportTarget, sheets: dict[str, list[list[Any]]]) -> tuple[str, list[list[Any]]]:
    """The sheet to import: one named like the module, else the first that isn't Instructions or Lists."""
    for name, rows in sheets.items():
        if header_key(name) in (header_key(target.title), header_key(target.plural)):
            return name, rows
    for name, rows in sheets.items():
        if header_key(name) not in ("instructions", "lists") and trim_rows(rows):
            return name, rows
    raise FileRefusal("The file has no rows to import.")


def _header_lookup(columns: list[Column], directory: Directory) -> tuple[dict[str, Column], dict[str, Column], dict[str, Slot]]:
    by_label = {header_key(c.label): c for c in columns}
    by_api = {c.api_name: c for c in columns}
    by_choice: dict[str, Slot] = {}
    for column in columns:
        if column.type != "multiselect":
            continue
        # Every choice, not only a short list's — a sheet built by hand may spread any field.
        for key, label, active in directory.options(column.picklist):
            if active:
                by_choice[choice_key(choice_header(column, label))] = Slot(column, key, label)
    return by_label, by_api, by_choice


def _slot_for(text: str, lookup, overrides: dict[str, str] | None) -> Slot | None:
    by_label, by_api, by_choice = lookup
    if overrides and text in overrides:
        chosen = overrides[text]
        column = by_api.get(chosen) if chosen else None
        return Slot(column) if column else None
    column = by_label.get(header_key(text)) or by_api.get(text.strip())
    if column:
        return Slot(column)
    return by_choice.get(choice_key(text))


def map_columns(
    columns: list[Column],
    sheet: str,
    rows: list[list[Any]],
    overrides: dict[str, str] | None,
    directory: Directory,
) -> Mapping:
    """
    Find the label row — row 3 of ARK's sample file, row 1 of most others — as
    the row among the first few whose cells name the most fields.
    """
    if not rows:
        raise FileRefusal("The sheet is empty.")
    lookup = _header_lookup(columns, directory)

    def score(row: list[Any]) -> int:
        return sum(1 for raw in row if raw is not None and str(raw).strip() and _slot_for(str(raw).strip(), lookup, None))

    header_index = max(range(min(len(rows), HEADER_SEARCH_ROWS)), key=lambda i: (score(rows[i]), -i))
    if score(rows[header_index]) == 0:
        header_index = 0
    header = rows[header_index]

    by_index: dict[int, Slot] = {}
    unmapped: list[str] = []
    seen: set[tuple[str, str | None]] = set()
    duplicates: list[str] = []
    for index, raw in enumerate(header):
        text = str(raw).strip() if raw is not None else ""
        if not text:
            continue
        slot = _slot_for(text, lookup, overrides)
        if slot is None:
            unmapped.append(text)
            continue
        identity = (slot.column.api_name, slot.choice)
        if identity in seen:
            duplicates.append(choice_header(slot.column, slot.choice_label) if slot.choice else slot.column.label)
            continue
        seen.add(identity)
        by_index[index] = slot
    return Mapping(sheet=sheet, header_index=header_index, header_row=header, by_index=by_index, unmapped=unmapped, duplicates=duplicates)


def _refusal_lines(exc: HTTPException) -> list[str]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message") or "This row was refused."
        details = [d for d in detail.get("details") or [] if isinstance(d, str)]
        return [message, *details]
    if isinstance(detail, str):
        return [detail]
    return ["This row was refused."]


def _validation_lines(exc: ValidationError, labels: dict[str, str]) -> list[str]:
    out = []
    for error in exc.errors():
        name = str(error.get("loc", ["?"])[-1])
        out.append(f"{labels.get(name, name.replace('_', ' '))}: {error.get('msg', 'is not valid')}")
    return out


class _Visibility:
    """Whether a column applies to a row, decided only where ARK can decide it for certain."""

    def __init__(self, target: ImportTarget, columns: list[Column], directory: Directory):
        self.directory = directory
        self.picklist_of = {c.api_name: c.picklist for c in columns}
        labels = {c.api_name: c.label for c in columns}
        self.defaults: dict[str, Any] = {}
        for name, info in getattr(target.schema, "model_fields", {}).items():
            if not info.is_required() and info.default is not None:
                self.defaults[name] = info.default
        self.rules: dict[str, tuple[str, str]] = {}  # api_name -> (expression, in words)
        for column in columns:
            expr = column.visibility_condition
            if not expr:
                continue
            try:
                names = {text for kind, text in _tokens(expr) if kind == "id"}
            except ConditionError:
                continue
            if column.api_name in names:
                continue  # "shown once filled in" — a value never hides itself
            if not names <= set(labels):
                continue  # reads a field no sheet carries; ARK can't know, so it keeps the value
            words = condition_in_words(expr, labels, directory, self.picklist_of)
            self.rules[column.api_name] = (expr, words or "some other answers allow it")

    def hidden(self, api_name: str, payload: dict[str, Any]) -> str | None:
        """The rule in words, when this column doesn't apply to this row; else None."""
        rule = self.rules.get(api_name)
        if not rule:
            return None
        try:
            applies = evaluate(
                rule[0],
                value_of=lambda name: payload.get(name, self.defaults.get(name)),
                label_of=lambda name, key: self.directory.label(self.picklist_of.get(name), key),
            )
        except ConditionError:
            return None
        return None if applies else rule[1]


def run_import(
    db: Session,
    target: ImportTarget,
    sheets: dict[str, list[list[Any]]],
    *,
    user: User,
    overrides: dict[str, str] | None,
    answers: dict[str, dict[str, str]] | None = None,
    commit: bool,
) -> dict[str, Any]:
    columns = columns_for(db, target)
    labels = {c.api_name: c.label for c in columns}
    directory = Directory(db)
    sheet, raw_rows = pick_sheet(target, sheets)
    rows = trim_rows(raw_rows)
    mapping = map_columns(columns, sheet, rows, overrides, directory)
    visibility = _Visibility(target, columns, directory)
    answers = answers or {}

    def header_of(index: int) -> str:
        return str(mapping.header_row[index]).strip()

    report: dict[str, Any] = {
        "sheet": sheet,
        "header_row": mapping.header_index + 1,
        "columns": [
            {"header": header_of(i), "field": mapping.by_index[i].column.api_name if i in mapping.by_index else None}
            for i, h in enumerate(mapping.header_row)
            if h is not None and str(h).strip()
        ],
        "fields": [{"api_name": c.api_name, "label": c.label} for c in columns],
        "unmapped": mapping.unmapped,
        "total": 0,
        "ready": 0,
        "failed": 0,
        "warned": 0,
        "errors": [],
        "warnings": [],
        "unknown_values": [],
        "missing_records": [],
        "committed": False,
        "created": [],
    }

    if mapping.duplicates:
        raise FileRefusal(f"Two columns fill the same field: {', '.join(mapping.duplicates)}. Remove one of them.")
    if target.name_field not in {s.column.api_name for s in mapping.by_index.values()}:
        raise FileRefusal(f"The file needs a “{labels.get(target.name_field, target.name_field)}” column.")

    # Rows 4-5 of a sample file — what to enter, and when — sit right under the labels.
    expected_hints = {
        index: how_to_fill(slot.column, choice=bool(slot.choice)) for index, slot in mapping.by_index.items()
    }
    first = mapping.header_index + 1
    while first < len(rows) and first <= mapping.header_index + 2 and is_guidance_row(rows[first], expected_hints):
        first += 1

    data_rows = [
        (excel_row, row)
        for excel_row, row in enumerate(rows[first:], start=first + 1)
        if not all(is_blank(cell) for cell in row)
    ]
    report["total"] = len(data_rows)
    if not data_rows:
        raise FileRefusal("The sheet has headers but no rows to import.")
    if len(data_rows) > MAX_ROWS:
        raise FileRefusal(f"The file has {len(data_rows):,} rows. Import at most {MAX_ROWS:,} at a time.")

    unknown: dict[tuple[str, str], int] = {}
    missing: dict[str, dict[str, int]] = {}

    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        # The importing user, attached to this session so relationship reads work.
        acting = session.get(User, user.user_id)
        for excel_row, row in data_rows:
            problems: list[str] = []
            notes: list[str] = []
            payload: dict[str, Any] = dict(target.defaults)
            picked: dict[str, list[str]] = {}
            for index, slot in mapping.by_index.items():
                column = slot.column
                raw = row[index] if index < len(row) else None
                if slot.choice:
                    try:
                        if read_checkbox(raw):
                            picked.setdefault(column.api_name, []).append(slot.choice)
                        else:
                            picked.setdefault(column.api_name, [])
                    except CellError as exc:
                        problems.append(f"{choice_header(column, slot.choice_label or '')}: {exc}")
                    continue
                try:
                    value = read_cell(column, raw, directory, answers.get(column.api_name))
                except CellError as exc:
                    if column.api_name == target.stage_field:
                        value = _NOT_A_STAGE  # said once, below, in the stage's own words
                    else:
                        if isinstance(exc, UnknownChoice):
                            unknown[(column.api_name, exc.text)] = unknown.get((column.api_name, exc.text), 0) + 1
                        elif isinstance(exc, MissingRecord):
                            names = missing.setdefault(column.api_name, {})
                            names[exc.text] = names.get(exc.text, 0) + 1
                        problems.append(f"{column.label}: {exc}")
                        continue
                if value is not None:
                    payload[column.api_name] = value

            # A multi-choice field read from its Yes/No columns, plus any combined column.
            for api_name, keys in picked.items():
                merged = list(payload.get(api_name) or [])
                merged.extend(k for k in keys if k not in merged)
                if merged:
                    payload[api_name] = merged

            # A value in a column that doesn't apply to this row is left out, not refused.
            for api_name in [k for k in payload if k in visibility.rules]:
                if is_blank(payload.get(api_name)) or payload.get(api_name) == []:
                    continue
                rule = visibility.hidden(api_name, payload)
                if rule:
                    payload.pop(api_name)
                    notes.append(f"{labels.get(api_name, api_name)}: left out, because it's used only if {rule}.")

            if is_blank(payload.get(target.name_field)):
                problems.append(f"{labels.get(target.name_field, target.name_field)} is required.")

            if target.stage_field:
                stage_key = payload.get(target.stage_field)
                allowed = [k for k, _, active in directory.options(target.stage_picklist) if active and _stage_number(k) is not None and _stage_number(k) <= (target.max_stage or 0)]
                if stage_key is None and allowed:
                    payload[target.stage_field] = allowed[0]
                elif stage_key not in allowed:
                    payload.pop(target.stage_field, None)
                    problems.append(
                        f"{labels.get(target.stage_field, 'Stage')}: import new {target.plural.lower()} at Stage 0, "
                        "then move them forward in ARK, where the move's checks are recorded."
                    )

            if target.row_rule and not problems:
                message = target.row_rule(payload, directory)
                if message:
                    problems.append(message)

            if not problems:
                try:
                    model = target.schema.model_validate(payload)
                except ValidationError as exc:
                    problems.extend(_validation_lines(exc, labels))

            if not problems:
                try:
                    report["created"].append(target.create(model, session, acting))
                except HTTPException as exc:
                    session.rollback()
                    lines = _refusal_lines(exc)
                    if isinstance(exc.detail, dict) and exc.detail.get("code") == "POSSIBLE_DUPLICATE":
                        reason = labels.get("not_duplicate_reason")
                        lines = [
                            "This End Client already has an open pursuit.",
                            f"Different project: fill in “{reason}” on this row." if reason else "Add it from the Leads screen instead.",
                            "Same project: add it from the Leads screen, where you can join its group.",
                        ]
                    problems.extend(lines)
                except Exception:  # a bug, not a refusal — reported, never half-applied
                    session.rollback()
                    problems.append("ARK couldn't save this row. Nothing was imported. Send us feedback if it keeps happening.")

            if problems:
                report["failed"] += 1
                if len(report["errors"]) < MAX_REPORTED_ROWS:
                    report["errors"].append({"row": excel_row, "messages": problems})
            else:
                report["ready"] += 1
                if notes:
                    report["warned"] += 1
                    if len(report["warnings"]) < MAX_REPORTED_ROWS:
                        report["warnings"].append({"row": excel_row, "messages": notes})

        if commit and report["failed"] == 0:
            outer.commit()
            report["committed"] = True
        else:
            outer.rollback()
            report["created"] = []
    except Exception:
        outer.rollback()
        raise
    finally:
        session.close()
        connection.close()

    by_api = {c.api_name: c for c in columns}
    report["unknown_values"] = [
        {
            "field": api_name,
            "label": labels.get(api_name, api_name),
            "value": text,
            "rows": count,
            "choices": [{"key": k, "label": label} for k, label, active in directory.options(by_api[api_name].picklist) if active],
        }
        for (api_name, text), count in unknown.items()
    ]
    report["missing_records"] = [
        {
            "field": api_name,
            "label": labels.get(api_name, api_name),
            "noun": _noun(by_api[api_name].lookup_target),
            "names": list(names)[:MAX_NAMES_REPORTED],
            "count": len(names),
            "rows": sum(names.values()),
        }
        for api_name, names in missing.items()
    ]
    return report


def _stage_number(key: str) -> int | None:
    head = key.split("_", 1)[0]
    return int(head) if head.isdigit() else None


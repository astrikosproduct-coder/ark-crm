"""
Which fields a spreadsheet carries, and how a cell becomes a stored value.

Everything comes from the field register (app/metadata_resolver.py) and the
sidecar spec/extensions.json — the same two sources the forms read — so a
field added, renamed or relabelled in Administration shows up in the next
template without a code change (CLAUDE.md hard rule 3).

A cell is read the way a person would write it: a picklist by its label or its
key, a lookup by the record's name (or its id), a date as 17 Sep 2026 or an
Excel date, a checkbox as Yes/No. What cannot be read is an error on that row,
in plain words — never a guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..metadata_resolver import resolved_fields
from ..metadata_spec import SPEC_DIR
from ..models import Account, Contact, Deal, DealRegistration, Lead, PicklistValue, User
from .conditions import ConditionError, evaluate, slug

# ------------------------------------------------------------------ the sidecar


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _extensions_at(mtime: float) -> dict[str, Any]:
    return _read_json(SPEC_DIR / "extensions.json")


def extensions() -> dict[str, Any]:
    """spec/extensions.json, re-read whenever the file changes."""
    return _extensions_at((SPEC_DIR / "extensions.json").stat().st_mtime)


def extension_of(module: str, api_name: str) -> dict[str, Any]:
    entry = extensions().get("fields", {}).get(f"{module}.{api_name}")
    return entry if isinstance(entry, dict) else {}


@lru_cache(maxsize=4)
def _products_at(mtime: float) -> list[dict[str, Any]]:
    return _read_json(SPEC_DIR / "seed" / "products.json")


def products() -> list[dict[str, Any]]:
    """The product catalogue is still seed data in the browser store, read from the same file."""
    path = SPEC_DIR / "seed" / "products.json"
    return _products_at(path.stat().st_mtime) if path.exists() else []


# ------------------------------------------------------------------ columns

#: Types a cell can carry. Files, child lists (their own sheets), formulas and
#: autonumbers are never read from a column.
READABLE_TYPES = {
    "text", "longtext", "richtext", "url", "email", "phone",
    "number", "currency", "percent", "date", "datetime", "checkbox",
    "picklist", "multiselect", "lookup",
}

#: Set by the server on every save, or by the stage — never typed in.
NEVER_IMPORTED = {
    "created_by", "created_date", "modified_by", "modified_date",
    "created_by_date", "modified_by_date",
    "progression_pct", "probability_pct", "progression_default_pct", "probability_default_pct",
    "probability_override_justification", "stage_skip_reason", "stage_reversal_reason",
    "lead_status", "is_primary_pursuit", "pursuit_group", "active",
}

#: Not editable on the form, but answered in the app by a dialog — a sheet has no
#: dialog, so the answer is a column. `not_duplicate_reason` is what the
#: duplicate-pursuit dialog writes when someone says "a different project".
DIALOG_ANSWERS = {("leads", "not_duplicate_reason")}

#: Lookup targets a sheet can resolve by name.
RESOLVABLE_TARGETS = {"account", "user", "contact", "deal_registration", "deal", "product", "lead"}


@dataclass
class Column:
    api_name: str
    label: str
    type: str
    section: str
    picklist: str | None = None
    lookup_target: str | None = None
    lookup_filter_expr: str | None = None
    requirement: str | None = None
    mandatory_from: int | None = None
    visibility_condition: str | None = None
    condition: str | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    description: str | None = None
    #: Ticked "Required when creating" in Administration (migration 0037).
    required_on_create: bool = False


def _published_rows(db: Session, module: str) -> list[dict[str, Any]]:
    """
    The module's fields as last PUBLISHED — what a save is checked against
    (app/requirements.py), so the sample file and the import follow the same
    version the app runs on. An unpublished draft changes neither. Falls back to
    the draft only on a database never published.
    """
    from ..live_register import published  # local: live_register imports the metadata layer

    register = published(db)
    return register.fields_of(module) if register is not None else resolved_fields(db, module)


def _column(row: dict[str, Any], module: str) -> Column:
    ext = extension_of(module, row["api_name"])
    return Column(
        api_name=row["api_name"],
        label=ext.get("label_override") or row["label"],
        # A recorded departure wins, exactly as the form engine applies it —
        # sap_solution_suite is a lookup in the register and free text on screen.
        type=ext.get("type_override") or row["type"],
        section=row["section"],
        picklist=row["picklist"],
        lookup_target=row["lookup_target"],
        lookup_filter_expr=ext.get("lookup_filter_expr"),
        requirement=row["requirement"],
        mandatory_from=row["mandatory_from"],
        visibility_condition=row["visibility_condition"],
        condition=row["condition"],
        max_length=row["max_length"],
        min_value=float(row["min_value"]) if row.get("min_value") is not None else None,
        max_value=float(row["max_value"]) if row.get("max_value") is not None else None,
        description=row.get("description"),
        required_on_create=bool(row.get("required_on_create")),
    )


def register_columns(db: Session, module: str) -> list[Column]:
    """Every active field of a module, in form order — the export's view."""
    return [_column(row, module) for row in _published_rows(db, module)]


def import_columns(db: Session, module: str, *, max_stage: int | None) -> list[Column]:
    """
    The fields an import sheet offers: owned by this record, typed in by a
    person, and — for a staged module — captured no later than `max_stage`.
    """
    out: list[Column] = []
    for row in _published_rows(db, module):
        ext = extension_of(module, row["api_name"])
        if row["value_mode"] != "own":
            continue
        if not row["editable"] and (module, row["api_name"]) not in DIALOG_ANSWERS:
            continue
        if row["type"] not in READABLE_TYPES or row["requirement"] in ("System", "Computed"):
            continue
        if row["api_name"] in NEVER_IMPORTED or ext.get("phase1_locked"):
            continue
        if row.get("stage_scoped") not in (None, "none"):
            continue  # a per-stage answer belongs to a stage move, not to a new record
        if row["type"] == "lookup" and row["lookup_target"] not in RESOLVABLE_TARGETS:
            continue
        if max_stage is not None:
            captured = row["capture_stage"]
            required_from = row["mandatory_from"]
            if captured is not None and captured > max_stage:
                continue
            if captured is None and required_from is not None and required_from > max_stage:
                continue
        out.append(_column(row, module))
    return out


def child_columns(module: str, api_name: str) -> tuple[str, list[Column]] | None:
    """A child list's own columns, from its child_spec in the sidecar."""
    spec = extension_of(module, api_name).get("child_spec")
    if not spec:
        return None
    columns: list[Column] = []
    for entry in spec.get("columns", []):
        if isinstance(entry, str):
            ref_module, _, ref_name = entry.partition(".")
            ref = extension_of(ref_module, ref_name)
            columns.append(Column(api_name=ref_name, label=ref.get("label_override") or ref_name.replace("_", " ").title(), type="text", section=""))
            continue
        if entry.get("computed_expr") or entry.get("type") not in READABLE_TYPES:
            continue
        columns.append(
            Column(
                api_name=entry["api_name"],
                label=entry.get("label") or entry["api_name"],
                type=entry["type"],
                section="",
                picklist=entry.get("picklist"),
                lookup_target=entry.get("lookup_target"),
                lookup_filter_expr=entry.get("lookup_filter_expr"),
                requirement="Mandatory" if entry.get("required") else "Optional",
                max_length=entry.get("max_length"),
            )
        )
    return spec.get("label") or api_name, columns


def section_title(section: str) -> str:
    """A register section as a person reads it: "STAGE 0 — CONNECT" → "Stage 0 - Connect"."""
    text = re.sub(r"\s+", " ", section.replace("—", "-").replace("·", "-")).strip()
    if text.upper() == text:
        text = text.title().replace("Poc", "POC").replace("Rfp", "RFP").replace("Rfi", "RFI")
    if text.lower().startswith("read through the parent"):
        return "From the Lead"
    return text


# ------------------------------------------------------------------ lookups and picklists


@dataclass
class Target:
    id: str
    name: str
    extra: str | None = None  # a second name to match on — a user's email, a product's SKU
    attrs: dict[str, Any] = field(default_factory=dict)


class Directory:
    """Picklists and lookup targets, loaded once per request."""

    def __init__(self, db: Session):
        self.db = db
        self._picklists: dict[str, list[tuple[str, str, bool]]] = {}
        self._targets: dict[str, list[Target]] = {}

    # ---- picklists
    def options(self, picklist: str | None) -> list[tuple[str, str, bool]]:
        if not picklist:
            return []
        if picklist not in self._picklists:
            rows = self.db.scalars(
                select(PicklistValue).where(PicklistValue.picklist_key == picklist).order_by(PicklistValue.sort_order)
            )
            self._picklists[picklist] = [(r.key, r.label, r.active) for r in rows]
        return self._picklists[picklist]

    def label(self, picklist: str | None, key: Any) -> str | None:
        return next((label for k, label, _ in self.options(picklist) if k == key), None)

    # ---- lookup targets
    def targets(self, target: str | None) -> list[Target]:
        if not target:
            return []
        if target in self._targets:
            return self._targets[target]
        db = self.db
        if target == "account":
            rows = [
                Target(a.account_id, a.account_name, attrs={"account_type": sorted(t.account_type for t in a.types), "active": getattr(a, "active", True)})
                for a in db.scalars(select(Account))
            ]
        elif target == "user":
            rows = [
                Target(u.user_id, u.name, u.email, attrs={"roles": [r.role_id for r in u.roles], "active": getattr(u, "active", True)})
                for u in db.scalars(select(User))
            ]
        elif target == "contact":
            rows = [Target(c.contact_id, c.full_name, c.email, attrs={"active": getattr(c, "active", True)}) for c in db.scalars(select(Contact))]
        elif target == "deal_registration":
            rows = [Target(r.registration_id, r.project_name or r.registration_id) for r in db.scalars(select(DealRegistration))]
        elif target == "deal":
            rows = [Target(d.deal_id, d.deal_name or d.deal_id) for d in db.scalars(select(Deal))]
        elif target == "lead":
            rows = [Target(l.lead_id, l.opportunity_name or l.lead_id) for l in db.scalars(select(Lead))]
        elif target == "product":
            rows = [Target(p["sku"], p["name"], p["sku"], attrs=dict(p)) for p in products()]
        else:
            rows = []
        self._targets[target] = rows
        return rows

    def name_of(self, target: str | None, record_id: Any) -> str | None:
        return next((t.name for t in self.targets(target) if t.id == record_id), None)


# ------------------------------------------------------------------ cells

_BLANK = re.compile(r"^\s*$")
_TRUE = {"yes", "y", "true", "1", "x", "✓"}
_FALSE = {"no", "n", "false", "0"}

#: Dates written with the month as a word are never ambiguous.
_WORD_DATES = (
    "%d-%b-%Y", "%d %b %Y", "%d/%b/%Y", "%d-%B-%Y", "%d %B %Y",
    "%b %d %Y", "%b %d, %Y", "%B %d %Y", "%B %d, %Y", "%d-%b-%y", "%d %b %y",
)
_WORD_MONTHS = ("%b-%Y", "%b %Y", "%B-%Y", "%B %Y", "%b-%y")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_ISO_DATE = re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?:[ T].*)?$")
_NUMERIC_MONTH = re.compile(r"^(?:(\d{1,2})[/.\-](\d{4})|(\d{4})[/.\-](\d{1,2}))$")

#: A lookup cell may carry the record id after the name — the sample file's
#: dropdown does that only where two records share a name.
_NAME_AND_ID = re.compile(r"^(?P<name>.*\S)\s*\((?P<id>[A-Z]+-\d+)\)$")

#: A multi-choice field with at most this many choices gets one Yes/No column
#: per choice in the sample file, so nobody has to type a choice's exact words.
SPLIT_CHOICE_LIMIT = 6


def is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and bool(_BLANK.match(raw)))


def _date_or_none(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _as_date(raw: Any, *, month: bool) -> date:
    """
    A real Excel date, or text in a form that can only mean one date.

    03/04/2026 is 3 April in Dubai and 4 March in the US, and nothing in the
    cell says which. It is refused rather than guessed. 25/03/2026 can only be
    one date, so it is read.
    """
    if isinstance(raw, datetime):
        found = raw.date()
    elif isinstance(raw, date):
        found = raw
    else:
        found = _parse_date_text(str(raw).strip(), month=month)
    return found.replace(day=1) if month else found


def _parse_date_text(text: str, *, month: bool) -> date:
    example = "Oct-2026" if month else "17-Sep-2026"
    for fmt in _WORD_DATES:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if match := _ISO_DATE.match(text):
        found = _date_or_none(int(match[1]), int(match[2]), int(match[3]))
        if found:
            return found
    if match := _NUMERIC_DATE.match(text):
        a, b, year = int(match[1]), int(match[2]), int(match[3])
        day_first, month_first = _date_or_none(year, b, a), _date_or_none(year, a, b)
        if day_first and month_first and day_first != month_first:
            raise ValueError(
                f"“{text}” could be {day_first:%d %B} or {month_first:%d %B} — write it as {day_first:%d-%b-%Y} or {month_first:%d-%b-%Y}"
            )
        if day_first or month_first:
            return day_first or month_first  # type: ignore[return-value]
    for fmt in _WORD_MONTHS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if match := _NUMERIC_MONTH.match(text):
        number, year = (int(match[1]), int(match[2])) if match[1] else (int(match[4]), int(match[3]))
        found = _date_or_none(year, number, 1)
        if found:
            return found
    raise ValueError(f"enter a {'month' if month else 'date'} like {example}")


def _as_number(raw: Any) -> float:
    if isinstance(raw, bool):
        raise ValueError("enter a number")
    if isinstance(raw, (int, float, Decimal)):
        return float(raw)
    text = re.sub(r"[,\s]|[A-Za-z$€£₹]+$|^[A-Za-z$€£₹]+", "", str(raw))
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        raise ValueError("enter a number") from None


class CellError(ValueError):
    """A cell that cannot be read. The message is shown to the person importing."""


class UnknownChoice(CellError):
    """Text that is not one of a dropdown's choices — answered once for every row that has it."""

    def __init__(self, text: str):
        super().__init__(f"“{text}” isn't one of the choices")
        self.text = text


class MissingRecord(CellError):
    """A name with no record in ARK — reported once per field, with every name missing."""

    def __init__(self, text: str, noun: str):
        super().__init__(f"no {noun} called “{text}” in ARK")
        self.text = text


def matches_filter(expr: str | None, target: Target, directory: Directory) -> bool:
    if not expr:
        return True
    picklist_of = {"account_type": "accounts__account_type"}
    try:
        return evaluate(
            expr,
            value_of=lambda name: target.attrs.get(name),
            label_of=lambda name, key: directory.label(picklist_of.get(name), key),
        )
    except ConditionError:
        return True  # an expression the server cannot read never blocks a pick the form would allow


def split_choices(column: Column, directory: Directory) -> list[tuple[str, str]]:
    """(key, label) per choice when the sample file gives each its own Yes/No column; else []."""
    if column.type != "multiselect":
        return []
    options = [(k, label) for k, label, active in directory.options(column.picklist) if active]
    return options if 0 < len(options) <= SPLIT_CHOICE_LIMIT else []


def lookup_choices(column: Column, directory: Directory) -> list[str]:
    """
    What the sample file's dropdown offers for a lookup: every record the form
    would let you pick, by name. Two records with one name are told apart by
    their id — the only place an id is shown, because the name alone can't do it.
    """
    eligible = [
        t for t in directory.targets(column.lookup_target)
        if t.attrs.get("active", True) is not False and matches_filter(column.lookup_filter_expr, t, directory)
    ]
    counts: dict[str, int] = {}
    for t in eligible:
        counts[slug(t.name)] = counts.get(slug(t.name), 0) + 1
    names = [t.name if counts[slug(t.name)] == 1 else f"{t.name} ({t.id})" for t in eligible]
    return sorted(names, key=str.lower)


def read_checkbox(raw: Any) -> bool | None:
    if is_blank(raw):
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise CellError("enter Yes or No")


def read_cell(column: Column, raw: Any, directory: Directory, answers: dict[str, str] | None = None) -> Any:
    """
    The stored value for one cell, or CellError. A blank cell is None.

    `answers` is what the person said, on the review screen, a choice's
    unrecognised text means: {"SI": "PARTNER_SI"}, or "" to leave it out.
    """
    if is_blank(raw):
        return None
    kind = column.type

    if kind in ("text", "longtext", "richtext", "url", "email", "phone"):
        text = str(raw).strip() if not isinstance(raw, float) or not raw.is_integer() else str(int(raw))
        if column.max_length and len(text) > column.max_length:
            raise CellError(f"is too long — {column.max_length} characters at most")
        return text

    if kind in ("number", "currency", "percent"):
        try:
            number = _as_number(raw)
        except ValueError as exc:
            raise CellError(str(exc)) from None
        if column.min_value is not None and number < column.min_value:
            raise CellError(f"must be at least {column.min_value:g}")
        if column.max_value is not None and number > column.max_value:
            raise CellError(f"must be at most {column.max_value:g}")
        return number

    if kind in ("date", "datetime"):
        try:
            return _as_date(raw, month=column.api_name.endswith("_month")).isoformat()
        except ValueError as exc:
            raise CellError(str(exc)) from None

    if kind == "checkbox":
        return read_checkbox(raw)

    if kind in ("picklist", "multiselect"):
        options = [(k, label) for k, label, active in directory.options(column.picklist) if active]
        keys = {k for k, _ in options}

        def match(text: str) -> str | None:
            want = slug(text)
            return next((k for k, label in options if slug(k) == want or slug(label) == want), None)

        def one(text: str) -> str | None:
            """A choice's key; None when the person chose to leave this text out."""
            hit = match(text)
            if hit is not None:
                return hit
            if answers and text in answers and (answers[text] == "" or answers[text] in keys):
                return answers[text] or None
            raise UnknownChoice(text)

        if kind == "picklist":
            return one(str(raw).strip())
        chosen: list[str] = []
        for part in (p.strip() for p in re.split(r"[;\n]", str(raw))):
            if not part:
                continue
            # "End Client, Partner / SI" — commas split only when every piece is a choice,
            # so a choice whose own label holds a comma still reads whole.
            pieces = [p.strip() for p in part.split(",") if p.strip()]
            if match(part) is None and len(pieces) > 1 and all(match(p) is not None for p in pieces):
                found = [match(p) for p in pieces]
            else:
                found = [one(part)]
            chosen.extend(k for k in found if k is not None and k not in chosen)
        return chosen or None

    if kind == "lookup":
        text = str(raw).strip() if not isinstance(raw, float) or not raw.is_integer() else str(int(raw))
        candidates = [t for t in directory.targets(column.lookup_target) if t.attrs.get("active", True) is not False]
        by_id = [t for t in candidates if t.id.lower() == text.lower()]
        tagged = _NAME_AND_ID.match(text)
        if not by_id and tagged:
            by_id = [t for t in candidates if t.id == tagged["id"] and slug(t.name) == slug(tagged["name"])]
        hits = by_id or [t for t in candidates if slug(t.name) == slug(text) or (t.extra and t.extra.lower() == text.lower())]
        if not hits:
            raise MissingRecord(text, _noun(column.lookup_target))
        allowed = [t for t in hits if matches_filter(column.lookup_filter_expr, t, directory)]
        if not allowed:
            raise CellError(f"“{text}” can't be picked here")
        if len(allowed) > 1:
            raise CellError(
                f"“{text}” matches {len(allowed)} {_noun(column.lookup_target)}s — pick it from the dropdown in the sample file"
            )
        return allowed[0].id

    raise CellError("can't be imported")


def _noun(target: str | None) -> str:
    return {"user": "person", "deal_registration": "registration"}.get(target or "", target or "record")


def display_value(column: Column, value: Any, directory: Directory, labels: dict[str, str] | None = None) -> Any:
    """What an export cell shows: labels and names, real dates and numbers."""
    if value is None or value == "" or value == []:
        return None
    kind = column.type
    if kind == "picklist":
        return directory.label(column.picklist, value) or value
    if kind == "multiselect":
        items = value if isinstance(value, list) else [value]
        return "; ".join(directory.label(column.picklist, v) or str(v) for v in items)
    if kind == "lookup":
        return (labels or {}).get(column.api_name) or directory.name_of(column.lookup_target, value) or value
    if kind == "checkbox":
        return "Yes" if value else "No"
    if kind in ("date", "datetime"):
        try:
            if isinstance(value, (date, datetime)):
                return value if kind == "datetime" else (value.date() if isinstance(value, datetime) else value)
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if kind == "datetime" else parsed.date()
        except ValueError:
            return value
    if kind in ("number", "currency", "percent", "computed"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value

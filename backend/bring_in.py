"""
Bring a BD owner's existing pipeline into ARK, each pursuit at the stage it is
really in (decided 14 Oct 2026, the ROB / "Amit - ARK Accounts & Pursuits" load).

    python bring_in.py "<workbook>.xlsx" --as <your email>            # dry run: a full rehearsal, rolled back
    python bring_in.py "<workbook>.xlsx" --as <your email> --apply    # all of it, or nothing

A DEVELOPER-RUN ONBOARDING TOOL, NEVER PART OF THE APP
-------------------------------------------------------
Leads are the one door and a stage move is the gate (CLAUDE.md). This script
keeps the first and, for the pursuits it brings in, relaxes the second ONCE:
every pursuit is created as a Lead, then moved and converted to its stage by
the same requests the Update Stage dialog sends, so each Opportunity and Deal
has its Lead, its conversion and its history. The one difference is the
"brought in at Stage N" rule: the required fields of the stages a pursuit has
already passed — Connect's, mostly — are not demanded on that move. It is
switched on in THIS process, for THAT request only (requirements.ENFORCED),
and only when the live rules refused the move for missing fields; nothing in
the running app can reach it. The report names every field it waived.

Each person is onboarded once; after that they enter pursuits in ARK.

THE WORKBOOK
------------
The ARK import template, two sheets (found by their columns, any names):

  Accounts   ARK's Accounts import columns. An account already in ARK — the
             same registered name in the same Country — is reused, not added.
  Pursuits   ARK's Leads import columns, plus two of the bring-in's own:
             ARK Stage   "4 - RFP / RFI". Blank means Stage 0 · Connect.
             Primary     Yes / No — only for one project pursued through two
                         partners (see below).

Two partners on one project are TWO ROWS with the same Opportunity Name and
End Client, one per Customer (Partner / SI), exactly one marked Primary = Yes.
They become two deal registrations, a conflict decided "Both pursued" with the
primary's registration first, and two Leads that join that pursuit group — the
secondary never counts in the pipeline (the head's rule: registrations only
for this case). Another project at the same End Client needs its row's
"Not a Duplicate — Reason", as on any import.

SAFE TO RUN AGAIN: a pursuit already in ARK (same Opportunity Name, End Client
and Customer) is skipped, so a re-run after fixing a few rows adds only those.

THE VALUE: the row's Estimated Value is the Lead's; an Opportunity carries it
as One-Time Revenue, so its TCV shows the same figure; a Deal as its Contract
Value, with the Opportunity's Final Negotiated Value equal to it (decided
14 Oct 2026). Probability and Progression are the landing stage's own.

Everything runs through the app's own routes, in-process, inside ONE database
transaction: a dry run is the real thing rolled back, and --apply commits only
when every row went in.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import openpyxl  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import requirements  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.clock import today_company  # noqa: E402
from app.database import engine, get_db  # noqa: E402

engine.echo = False

from app.live_register import published  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, Lead, User  # noqa: E402
from app.routers.spreadsheets import _import_target  # noqa: E402
from app.spreadsheets.fields import CellError, Directory, is_blank, read_cell, read_checkbox  # noqa: E402
from app.spreadsheets.importer import _Visibility, columns_for, map_columns  # noqa: E402
from app.spreadsheets.workbook import (  # noqa: E402
    choice_header,
    header_key,
    how_to_fill,
    is_guidance_row,
    trim_rows,
)

STAGE_COLUMN = "ARK Stage"
PRIMARY_COLUMN = "Primary"
LEAD_STAGES = ["0_CONNECT", "1_DEMO", "2_POC_PILOT", "3_PRESCRIPTION"]
OPPORTUNITY_STAGES = {4: "4_RFP_RFI", 5: "5_TECHNICAL_EVAL", 6: "6_COMMERCIAL_EVAL"}
DEAL_OPENING = "7_CLOSE"
#: Never copied blind from one record to the next — the frontend's STAGE_PCT_FIELDS.
STAGE_PCT_FIELDS = {"progression_pct", "probability_pct", "progression_default_pct", "probability_default_pct"}


# =========================================================================
# READING THE WORKBOOK — the importer's own column mapping and cell readers
# =========================================================================


@dataclass
class Row:
    sheet_row: int
    payload: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.payload.get("opportunity_name") or self.payload.get("account_name") or "").strip()


def load_sheets(path: str) -> dict[str, list[list[Any]]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


class SheetReader:
    """One sheet, read the way ARK's import reads it: labels, choices, lookups, dates."""

    def __init__(self, db: Session, module: str, sheets: dict[str, list[list[Any]]], answers: list[str] | None = None):
        self.db = db
        self.target = _import_target(module)
        self.columns = columns_for(db, self.target)
        self.labels = {c.api_name: c.label for c in self.columns}
        directory = Directory(db)
        self.answers = self._answers(directory, answers or [])
        best = None
        for name, raw in sheets.items():
            rows = trim_rows(raw)
            if not rows:
                continue
            mapping = map_columns(self.columns, name, rows, None, directory)
            mapped = {s.column.api_name for s in mapping.by_index.values()}
            if self.target.name_field in mapped and (best is None or len(mapping.by_index) > len(best[1].by_index)):
                best = (rows, mapping)
        if best is None:
            raise SystemExit(f"No sheet has a “{self.labels.get(self.target.name_field)}” column.")
        self.rows, self.mapping = best
        self.sheet = self.mapping.sheet
        header = self.mapping.header_row
        self.extra_index = {
            str(h).strip(): i for i, h in enumerate(header) if h is not None and i not in self.mapping.by_index
        }
        hints = {i: how_to_fill(s.column, choice=bool(s.choice)) for i, s in self.mapping.by_index.items()}
        name_at = next(i for i, s in self.mapping.by_index.items() if s.column.api_name == self.target.name_field)
        first = self.mapping.header_index + 1
        # Rows 4-5 of ARK's sample file say what to enter and when. A sheet
        # whose hints were reworded is still a sample file: a row right under
        # the labels whose name cell is empty or the name's own hint is guidance.
        while first < len(self.rows) and first <= self.mapping.header_index + 2:
            row = self.rows[first]
            name_cell = row[name_at] if name_at < len(row) else None
            if not (is_guidance_row(row, hints) or is_blank(name_cell) or str(name_cell).strip() == hints[name_at]):
                break
            first += 1
        self.data = [
            (n, r) for n, r in enumerate(self.rows[first:], start=first + 1) if not all(is_blank(c) for c in r)
        ]
        register = published(db)
        self.dependencies = register.dependencies.get(self.target.field_module, {}) if register else {}

    def _answers(self, directory: Directory, given: list[str]) -> dict[str, dict[str, str]]:
        """--answer "Country|UAE|United Arab Emirates" -> {"country": {"UAE": "AE"}}, for this sheet's fields."""
        out: dict[str, dict[str, str]] = {}
        for text in given:
            parts = [part.strip() for part in text.split("|")]
            if len(parts) != 3:
                raise SystemExit(f'--answer "{text}": write it as "Field|typed text|the choice it means".')
            label, typed, meant = parts
            column = next((c for c in self.columns if header_key(c.label) == header_key(label)), None)
            if column is None:
                continue  # a field of the other sheet
            key = next((k for k, lab, active in directory.options(column.picklist) if active and header_key(lab) == header_key(meant)), None)
            if key is None:
                raise SystemExit(f'--answer "{text}": “{meant}” is not a choice of {column.label}.')
            out.setdefault(column.api_name, {})[typed] = key
        return out

    def extra(self, row: list[Any], heading: str) -> Any:
        index = next((i for h, i in self.extra_index.items() if header_key(h) == header_key(heading)), None)
        return row[index] if index is not None and index < len(row) else None

    def read(self, sheet_row: int, row: list[Any]) -> Row:
        """One row as a create payload. A fresh Directory: accounts made earlier in this run are pickable."""
        directory = Directory(self.db)
        visibility = _Visibility(self.target, self.columns, directory)
        out = Row(sheet_row)
        picked: dict[str, list[str]] = {}
        typed: dict[str, Any] = {}
        for index, slot in self.mapping.by_index.items():
            column = slot.column
            raw = row[index] if index < len(row) else None
            typed[column.api_name] = raw
            try:
                if slot.choice:
                    if read_checkbox(raw):
                        picked.setdefault(column.api_name, []).append(slot.choice)
                    continue
                value = read_cell(column, raw, directory, self.answers.get(column.api_name))
            except CellError as exc:
                label = choice_header(column, slot.choice_label or "") if slot.choice else column.label
                out.problems.append(f"{label}: {exc}")
                continue
            if value is not None:
                out.payload[column.api_name] = value
        for api_name, keys in picked.items():
            merged = list(out.payload.get(api_name) or [])
            merged.extend(k for k in keys if k not in merged)
            if merged:
                out.payload[api_name] = merged
        # A label two parents share is read within the row's own parent, as the import does.
        for child, dep in self.dependencies.items():
            value, parent = out.payload.get(child), out.payload.get(dep["parent"])
            allowed = dep["map"].get(str(parent), []) if parent is not None else []
            if value is None or value in allowed or is_blank(typed.get(child)):
                continue
            want = re.sub(r"[\s_\-/]+", "", str(typed[child])).lower()
            picklist = next((c.picklist for c in self.columns if c.api_name == child), None)
            within = [
                k for k, label, active in directory.options(picklist)
                if active and k in allowed and want in (re.sub(r"[\s_\-/]+", "", k).lower(), re.sub(r"[\s_\-/]+", "", label).lower())
            ]
            if within:
                out.payload[child] = within[0]
        for api_name in [k for k in out.payload if k in visibility.rules]:
            rule = visibility.hidden(api_name, out.payload)
            if rule and not is_blank(out.payload.get(api_name)) and out.payload.get(api_name) != []:
                out.payload.pop(api_name)
                out.notes.append(f"{self.labels.get(api_name, api_name)}: left out, because it's used only if {rule}.")
        if is_blank(out.payload.get(self.target.name_field)):
            out.problems.append(f"{self.labels.get(self.target.name_field)} is required.")
        out.extra = {STAGE_COLUMN: self.extra(row, STAGE_COLUMN), PRIMARY_COLUMN: self.extra(row, PRIMARY_COLUMN)}
        return out


# =========================================================================
# THE APP, IN-PROCESS, INSIDE ONE TRANSACTION
# =========================================================================


class Refused(Exception):
    def __init__(self, lines: list[str], code: str | None = None, detail: Any = None):
        super().__init__("; ".join(lines))
        self.lines, self.code, self.detail = lines, code, detail


class Ark:
    """The real routes, one shared session: a route's commit releases a savepoint."""

    def __init__(self, operator_email: str):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        operator = self.db.scalar(select(User).where(func.lower(User.email) == operator_email.lower()))
        if operator is None or not operator.active or not operator.roles:
            raise SystemExit(f"{operator_email} is not an active ARK user with a role.")
        self.operator_id = operator.user_id

        def _db():
            yield self.db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[current_user] = lambda: self.db.get(User, self.operator_id)
        # No `with`: the app's start-up (and its month-end timer) never runs here.
        self.client = TestClient(app)
        self.waived: dict[str, int] = defaultdict(int)
        self.notes: dict[str, int] = defaultdict(int)

    def note(self, notes: list[str]) -> None:
        for n in notes:
            self.notes[n] += 1

    def call(self, method: str, url: str, body: Any = None) -> Any:
        try:
            r = self.client.request(method, url, json=body)
        except Exception as exc:  # a bug, not a refusal — reported, never half-applied
            self.db.rollback()
            raise Refused([f"ARK couldn't save this ({type(exc).__name__}: {exc})."]) from exc
        if r.status_code < 400:
            return r.json() if r.content else None
        self.db.rollback()
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
        if isinstance(detail, dict):
            lines = [detail.get("message") or "Refused."]
            fields = detail.get("fields") or []
            lines += [f"Missing: {', '.join(f['label'] for f in fields)}"] if fields else list(detail.get("details") or [])
            raise Refused(lines, detail.get("code"), detail)
        raise Refused([str(detail)])

    def call_brought_in(self, method: str, url: str, body: Any) -> Any:
        """Live rules first; only a refusal for missing fields is retried under the brought-in rule."""
        try:
            return self.call(method, url, body)
        except Refused as refused:
            if refused.code != "REQUIRED_FIELDS_MISSING":
                raise
            for f in refused.detail.get("fields") or []:
                self.waived[f["label"]] += 1
        requirements.ENFORCED = False
        try:
            return self.call(method, url, body)
        finally:
            requirements.ENFORCED = True

    def finish(self, commit: bool) -> None:
        (self.outer.commit if commit else self.outer.rollback)()
        self.db.close()
        self.connection.close()
        app.dependency_overrides.clear()


# =========================================================================
# ACCOUNTS
# =========================================================================


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def bring_in_accounts(ark: Ark, sheets, report: list[str], answers: list[str]) -> tuple[int, int, int]:
    reader = SheetReader(ark.db, "accounts", sheets, answers)
    report.append(f"\nACCOUNTS — sheet “{reader.sheet}”")
    added = reused = failed = 0
    parent_col = next((i for i, s in reader.mapping.by_index.items() if s.column.api_name == "parent_account"), None)
    # Heads of groups first, so a company naming its parent finds it.
    ordered = sorted(reader.data, key=lambda nr: parent_col is not None and not is_blank(nr[1][parent_col] if parent_col < len(nr[1]) else None))
    for sheet_row, raw in ordered:
        row = reader.read(sheet_row, raw)
        label = f"  row {sheet_row:>4}  {row.name or '(no name)'}"
        if row.problems:
            failed += 1
            report.append(f"{label}\n        ✗ " + "\n        ✗ ".join(row.problems))
            continue
        same = [
            a for a in ark.db.scalars(select(Account).where(Account.country == row.payload.get("country")))
            if slug(a.account_name) == slug(row.name)
        ]
        if same:
            reused += 1
            report.append(f"{label}  — already in ARK, reused")
            continue
        try:
            try:
                ark.call("POST", "/api/accounts", row.payload)
            except Refused as refused:
                if refused.code != "POSSIBLE_DUPLICATE_ACCOUNT":
                    raise
                names = ", ".join(m.get("account_name") or "" for m in (refused.detail.get("matches") or []))
                row.notes.append(f"A similar name is already in ARK ({names}); added as a different company.")
                ark.call("POST", "/api/accounts", {**row.payload, "different_company": True})
            added += 1
            ark.note(row.notes)
            report.append(label + "  — added")
        except Refused as refused:
            failed += 1
            report.append(f"{label}\n        ✗ " + "\n        ✗ ".join(refused.lines))
    return added, reused, failed


# =========================================================================
# PURSUITS
# =========================================================================


def stage_of(value: Any) -> int | None:
    if is_blank(value):
        return 0
    match = re.match(r"\s*(\d+)", str(value))
    return int(match.group(1)) if match else None


def is_yes(value: Any) -> bool:
    return str(value or "").strip().lower() in ("yes", "y", "true", "1")


def stage_label(stage: int, names: dict[int, str]) -> str:
    return f"Stage {stage} · {names.get(stage, '')}".rstrip(" ·")


@dataclass
class Pursuit:
    row: Row
    stage: int
    primary: bool = False
    registration: str | None = None


def bring_in_pursuits(ark: Ark, sheets, report: list[str], today: str, answers: list[str]) -> tuple[int, int, int]:
    reader = SheetReader(ark.db, "leads", sheets, answers)
    stage_names = {
        n: label.split(" ", 1)[-1] for n, label in enumerate(
            [lab for _, lab, active in Directory(ark.db).options("leads_stage") if active]
        )
    }
    reason = f"Imported on {today}: already at this stage."
    report.append(f"\nPURSUITS — sheet “{reader.sheet}”")

    pursuits: list[Pursuit] = []
    failed = skipped = added = 0
    for sheet_row, raw in reader.data:
        row = reader.read(sheet_row, raw)
        stage = stage_of(row.extra[STAGE_COLUMN])
        if stage is None or stage > 7:
            row.problems.append(f"{STAGE_COLUMN}: “{row.extra[STAGE_COLUMN]}” is not a stage from 0 to 7.")
        pursuits.append(Pursuit(row, stage or 0, is_yes(row.extra[PRIMARY_COLUMN])))

    # One project through two partners: rows sharing a name and an End Client.
    groups: dict[tuple[str, str], list[Pursuit]] = defaultdict(list)
    for p in pursuits:
        groups[(slug(p.row.name), str(p.row.payload.get("end_client") or ""))].append(p)
    for (_, client), members in groups.items():
        if len(members) < 2 or not client:
            continue
        partners = [m.row.payload.get("customer_partner_si") for m in members]
        primaries = [m for m in members if m.primary]
        problem = None
        if None in partners or len(set(partners)) != len(partners):
            problem = "Rows of one project need a different Customer (Partner / SI) each."
        elif len(primaries) != 1:
            problem = f"One project through {len(members)} partners: mark exactly one row “{PRIMARY_COLUMN}” = Yes."
        if problem:
            for m in members:
                m.row.problems.append(problem)

    existing_leads = list(ark.db.scalars(select(Lead)))

    def already_in(p: Pursuit) -> bool:
        payload = p.row.payload
        return any(
            slug(lead.opportunity_name) == slug(p.row.name)
            and lead.end_client == payload.get("end_client")
            and lead.customer_partner_si == payload.get("customer_partner_si")
            for lead in existing_leads
        )

    def line(p: Pursuit) -> str:
        partner = ""
        if p.row.payload.get("customer_partner_si"):
            account = ark.db.get(Account, p.row.payload["customer_partner_si"])
            partner = f" ({account.account_name})" if account else ""
        return f"  row {p.row.sheet_row:>4}  {p.row.name or '(no name)'}{partner}"

    def fail(p: Pursuit, lines: list[str]) -> None:
        nonlocal failed
        failed += 1
        report.append(f"{line(p)}\n        ✗ " + "\n        ✗ ".join(lines))

    done: set[int] = set()
    for p in pursuits:
        if id(p) in done:
            continue
        key = (slug(p.row.name), str(p.row.payload.get("end_client") or ""))
        members = groups[key] if len(groups[key]) > 1 and key[1] else [p]
        members = sorted(members, key=lambda m: not m.primary)  # the primary first
        done.update(id(m) for m in members)

        if any(m.row.problems for m in members):
            for m in members:
                fail(m, m.row.problems or ["Not brought in: another row of this project has a problem."])
            continue
        if all(already_in(m) for m in members):
            for m in members:
                skipped += 1
                report.append(f"{line(m)}  — already in ARK, skipped")
            continue

        try:
            if len(members) > 1:
                register_both_pursued(ark, members, today)
            for m in members:
                lead = ark.call("POST", "/api/leads", {
                    **m.row.payload,
                    "project_stage": LEAD_STAGES[0],
                    **({"partner_deal_registration": m.registration} if m.registration else {}),
                })
                lead_id = lead["lead_id"]
                if m.registration:
                    ark.call("PATCH", f"/api/registrations/{m.registration}", {"linked_lead": lead_id})
                where = move(ark, lead_id, m.stage, m.row.payload.get("estimated_value"), reason)
                added += 1
                tag = "" if len(members) == 1 else (" — primary" if m.primary else " — secondary")
                ark.note(m.row.notes)
                report.append(f"{line(m)}  → {where}, {stage_label(m.stage, stage_names)}{tag}")
        except Refused as refused:
            # One pursuit (or one project's rows) refused: everything it wrote is
            # undone by the route's savepoint; the run commits nothing anyway.
            for m in members:
                fail(m, refused.lines if m is members[0] else ["Not brought in: another row of this project was refused."])
    return added, skipped, failed


def register_both_pursued(ark: Ark, members: list[Pursuit], today: str) -> None:
    """Two partners, one project: a registration each, one conflict, decided Both pursued."""
    mine: list[str] = []
    for m in members:
        payload = m.row.payload
        body = {
            "partner": payload["customer_partner_si"],
            "end_client": payload["end_client"],
            "project_name": m.row.name,
            "currency": payload.get("currency") or "USD",
            "estimated_value": payload.get("estimated_value"),
        }
        try:
            reg = ark.call("POST", "/api/registrations", body)
        except Refused as refused:
            if refused.code != "POSSIBLE_CONFLICT":
                raise
            raise_with, dismiss = [], []
            for match in refused.detail.get("matches") or []:
                (raise_with if match["registration_id"] in mine else dismiss).append(match["registration_id"])
            different = str(payload.get("not_duplicate_reason") or "").strip()
            if dismiss and len(different) < 5:
                raise Refused([
                    "Another partner is registered at this End Client for a different project.",
                    "Fill in “Not a Duplicate — Reason” on this project's rows.",
                ]) from refused
            reg = ark.call("POST", "/api/registrations", {
                **body, "raise_conflict_with": raise_with, "not_conflict_with": dismiss, "not_conflict_reason": different,
            })
        m.registration = reg.get("registration_id") or reg["id"]
        mine.append(m.registration)

    primary = members[0]
    partner = ark.db.get(Account, primary.row.payload["customer_partner_si"])
    for conflict in ark.call("GET", "/api/conflicts"):
        if {conflict.get("registration_a"), conflict.get("registration_b")} <= set(mine) and not conflict.get("decision"):
            ark.call("PATCH", f"/api/conflicts/{conflict.get('conflict_id') or conflict['id']}", {
                "decision": "BOTH_PURSUED",
                "primary_registration": primary.registration,
                "decision_rationale": (
                    f"Both partners pursue this project; {partner.account_name if partner else 'the primary'} "
                    f"is the primary pursuit. Imported on {today}."
                ),
            })


def move(ark: Ark, lead_id: str, stage: int, value: Any, reason: str) -> str:
    """Stage 0 Lead -> its stage, by the requests the Update Stage dialog sends. Returns what it became."""
    if stage == 0:
        return "Lead"
    if stage <= 3:
        ark.call_brought_in("PUT", f"/api/leads/{lead_id}", {
            "project_stage": LEAD_STAGES[stage], **({"stage_skip_reason": reason} if stage > 1 else {}),
        })
        ark.call("POST", "/api/transitions", {
            "module": "leads", "record_id": lead_id, "from": 0, "to": stage,
            "reason": reason, "is_skip": stage > 1, "is_reversal": False, "attested": [],
        })
        return "Lead"

    register = published(ark.db)
    read_through = {
        module: {f["api_name"] for f in register.fields if f["module"] == module and f.get("value_mode") == "read_through"}
        for module in ("opportunities", "deals")
    } if register else {"opportunities": set(), "deals": set()}

    lead = ark.call("GET", f"/api/leads/{lead_id}")
    opp_stage = min(stage, 6)
    payload = {k: v for k, v in lead.items() if k != "id" and k not in read_through["opportunities"] and k not in STAGE_PCT_FIELDS}
    payload.update({
        "parent_lead": lead_id,
        "project_stage": OPPORTUNITY_STAGES[opp_stage],
        "lead_status": "OPEN",
        "conversion_note": f"Moved directly from Stage 0 to Opportunity Stage {opp_stage}, skipping its own "
                           f"remaining stages — {reason}",
    })
    opp = ark.call_brought_in("POST", "/api/opportunities", payload)
    opp_id = opp["opportunity_id"]
    if value is not None:
        ark.call("PATCH", f"/api/opportunities/{opp_id}", {
            "one_time_revenue": value, **({"final_negotiated_value": value} if stage == 7 else {}),
        })
    if stage <= 6:
        return "Opportunity"

    # What the Convert to Deal dialog sends: the Opportunity's values with its
    # Lead's read through them (name, End Client, partner) — a record read
    # carries only its own.
    opp = ark.call("GET", f"/api/opportunities/{opp_id}")
    lead = ark.call("GET", f"/api/leads/{lead_id}")
    merged = {**{k: v for k, v in lead.items() if v is not None}, **{k: v for k, v in opp.items() if v is not None}}
    deal = {k: v for k, v in merged.items() if k != "id" and k not in read_through["deals"] and k not in STAGE_PCT_FIELDS}
    for key in ("lead_id", "opportunity_id", "parent_lead", "lead_status", "project_stage", "__labels"):
        deal.pop(key, None)
    deal.update({
        "deal_name": lead.get("opportunity_name"),
        "lead_status": "OPEN",
        "parent_opportunity": opp_id,
        "deal_stage": DEAL_OPENING,
        "contract_value": value,
        "conversion_note": f"Moved to Deals from Stage 6 — {reason}",
    })
    ark.call_brought_in("POST", "/api/deals", deal)
    return "Deal"


# =========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Bring a pipeline workbook into ARK at each pursuit's stage.")
    parser.add_argument("workbook")
    parser.add_argument("--as", dest="operator", required=True, help="your ARK email — the records are created by you")
    parser.add_argument("--apply", action="store_true", help="commit; without it the run is rolled back")
    parser.add_argument(
        "--answer", action="append", default=[], metavar='"Field|typed|choice"',
        help='what an unrecognised choice means, e.g. "Country|UAE|United Arab Emirates" (repeatable)',
    )
    args = parser.parse_args()

    sheets = load_sheets(args.workbook)
    today = today_company().strftime("%d %b %Y")
    ark = Ark(args.operator)
    report: list[str] = []
    committed = False
    a_added = a_reused = a_failed = p_added = p_skipped = p_failed = 0
    try:
        a_added, a_reused, a_failed = bring_in_accounts(ark, sheets, report, args.answer)
        p_added, p_skipped, p_failed = bring_in_pursuits(ark, sheets, report, today, args.answer)
        committed = args.apply and a_failed + p_failed == 0
    finally:
        ark.finish(committed)
    failed = a_failed + p_failed

    print("\n".join(report))
    print("\n" + "=" * 74)
    print(f"Accounts:  {a_added} to add, {a_reused} already in ARK, {a_failed} refused")
    print(f"Pursuits:  {p_added} to bring in, {p_skipped} already in ARK, {p_failed} refused")
    if ark.notes:
        print("\nLeft out or noted (the rows still go in):")
        for text, count in sorted(ark.notes.items(), key=lambda kv: -kv[1]):
            print(f"  {count} row(s): {text}")
    if ark.waived:
        print("\nThe brought-in rule waived these (fields of stages the pursuits had already passed):")
        for label, count in sorted(ark.waived.items(), key=lambda kv: -kv[1]):
            print(f"  {label} — {count} pursuit(s)")
    if committed:
        print("\nApplied: everything above is in ARK.")
    elif args.apply:
        print("\nNOTHING WAS WRITTEN: fix the refused rows (✗) and run again.")
    else:
        print("\nDry run — nothing written." + (" Fix the refused rows (✗), then" if failed else "") + " re-run with --apply.")
    return 0 if (failed == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

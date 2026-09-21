"""
/api/spreadsheets/{module} — Excel import and export (UX roadmap item 4).

    GET  /spreadsheets/{module}/template?format=xlsx|csv   the sample file
    GET  /spreadsheets/{module}/export?<list filters>      what the list shows, as a workbook
    POST /spreadsheets/{module}/import/preview?filename=   check every row, save nothing
    POST /spreadsheets/{module}/import?filename=           save every row, or none

    import:  leads (Stage 0), accounts, contacts, partners
    export:  the same four, plus opportunities and deals

The upload is the raw file as the request body — read, checked and discarded;
nothing is stored (file upload stays out of scope). `mapping` is an optional
JSON object in the query, {"header as written": "api_name" | ""}, for a column
the automatic label match could not place. `answers` is another,
{"api_name": {"text as written": "CHOICE_KEY" | ""}}, for a choice the file
wrote in its own words — picked once on the review screen.

Its own prefix rather than /api/leads/export, because /api/leads/{lead_id}
would claim "export" as a lead id. Needs the handlers.ts passthrough and the
vite.config.ts proxy entry, both.
"""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..clock import now_utc
from ..database import get_db
from ..messages import refusal
from ..models import User
from ..routers import accounts, contacts, deals, leads, opportunities
from ..schemas import AccountCreate, ContactCreate, LeadCreate
from ..spreadsheets.exporter import ExportTarget, export_filename, export_workbook
from ..spreadsheets.fields import Directory, extensions
from ..spreadsheets.importer import ImportTarget, columns_for, run_import
from ..spreadsheets.workbook import FileRefusal, condition_in_words, condition_note, read_upload, template_csv, template_workbook

router = APIRouter(tags=["spreadsheets"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _partner_types() -> list[str]:
    return list((extensions().get("partner_roster") or {}).get("account_types") or [])


def _partner_rule(payload: dict, directory: Directory) -> str | None:
    types = set(payload.get("account_type") or [])
    wanted = _partner_types()
    if types & set(wanted):
        return None
    names = [directory.label("accounts__account_type", t) or t for t in wanted]
    return f"Account Type must include {' or '.join(names)} to appear on Partners."


def _create_account(payload, db, user) -> str:
    # The route itself: its response costs one query for owner names.
    return accounts.create_account(payload=payload, db=db, user=user)["id"]


def _create_contact(payload, db, user) -> str:
    return contacts.create_contact(payload=payload, db=db, user=user)["id"]


def _import_target(module: str) -> ImportTarget:
    if module == "leads":
        return ImportTarget(
            key="leads", field_module="leads", title="Leads", noun="lead", plural="Leads",
            name_field="opportunity_name", schema=LeadCreate, create=lambda payload, db, user: leads.insert_lead(payload, db, user).lead_id,
            max_stage=0, stage_field="project_stage", stage_picklist="leads_stage",
        )
    if module == "accounts":
        return ImportTarget(
            key="accounts", field_module="accounts", title="Accounts", noun="account", plural="Accounts",
            name_field="account_name", schema=AccountCreate, create=_create_account,
        )
    if module == "partners":
        return ImportTarget(
            key="partners", field_module="accounts", title="Partners", noun="partner", plural="Partners",
            name_field="account_name", schema=AccountCreate, create=_create_account, row_rule=_partner_rule,
        )
    if module == "contacts":
        return ImportTarget(
            key="contacts", field_module="contacts", title="Contacts", noun="contact", plural="Contacts",
            name_field="full_name", schema=ContactCreate, create=_create_contact,
        )
    if module in ("opportunities", "deals"):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            refusal(
                "IMPORT_NOT_OFFERED",
                f"{module.title()} can't be imported.",
                [f"{module.title()} are created by converting a record in ARK, so each keeps its history."],
            ),
        )
    raise HTTPException(status.HTTP_404_NOT_FOUND, refusal("NOT_FOUND", "There is nothing to import or export here."))


def _export_target(module: str, request: Request, db: Session) -> ExportTarget:
    def list_rows(fn):
        return lambda: fn(request=request, response=Response(), db=db)

    if module == "leads":
        return ExportTarget("leads", "leads", "leads", "Leads", "opportunity_name", list_rows(leads.list_leads))
    if module == "opportunities":
        return ExportTarget(
            "opportunities", "opportunities", "opportunities", "Opportunities", "opportunity_name",
            list_rows(opportunities.list_opportunities), child_module_of={"payment_milestones": "leads"},
        )
    if module == "deals":
        return ExportTarget("deals", "deals", "deals", "Deals", "deal_name", list_rows(deals.list_deals))
    if module == "accounts":
        return ExportTarget("accounts", "accounts", "accounts", "Accounts", "account_name", list_rows(accounts.list_accounts))
    if module == "partners":
        wanted = set(_partner_types())
        every = list_rows(accounts.list_accounts)
        return ExportTarget(
            "partners", "accounts", "partners", "Partners", "account_name",
            lambda: [r for r in every() if wanted & set(r.get("account_type") or [])],
        )
    if module == "contacts":
        return ExportTarget("contacts", "contacts", "contacts", "Contacts", "full_name", list_rows(contacts.list_contacts))
    raise HTTPException(status.HTTP_404_NOT_FOUND, refusal("NOT_FOUND", "There is nothing to export here."))


def _download(body: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


#: Required fields the create logic fills when a row leaves them blank, so the
#: sample does not star them: a new lead's Currency defaults to USD
#: (app/routers/leads.py::insert_lead).
FILLED_ON_CREATE = {"currency"}


@router.get("/spreadsheets/{module}/template")
def download_template(module: str, format: str = "xlsx", db: Session = Depends(get_db)):
    target = _import_target(module)
    # The stage column is read when a file has one (to explain why only Stage 0
    # imports) but never offered: every imported lead starts at Stage 0.
    columns = [c for c in columns_for(db, target) if c.api_name != target.stage_field]
    # The name first — it is the column that stays in view — then each section's
    # columns together, in the order the form first shows that section.
    section_order: dict[str, int] = {}
    for column in columns:
        section_order.setdefault(column.section, len(section_order))
    columns.sort(key=lambda c: (c.api_name != target.name_field, section_order[c.section]))
    directory = Directory(db)
    labels = {c.api_name: c.label for c in columns}
    picklists = {c.api_name: c.picklist for c in columns}

    # The same rule a save applies (app/requirements.py, 21 Sep 2026), read off
    # the published register so Administration's changes show here too:
    #   Leads              the fields ticked "Required when creating" — every
    #                      other Mandatory one is needed when the lead moves on
    #   Accounts, Contacts every Mandatory field, on every save
    # A Conditional one is starred as well; row 5 says when it applies.
    demanded = {"Mandatory", "Conditional"}
    if target.stage_field:
        required = {
            c.api_name for c in columns
            if c.required_on_create and c.requirement in demanded and c.api_name not in FILLED_ON_CREATE
        }
        later = {c.api_name for c in columns if c.requirement == "Mandatory" and c.api_name not in required}
    else:
        required = {c.api_name for c in columns if c.requirement == "Mandatory" or (c.requirement == "Conditional" and c.condition)}
        later = set()
    required.add(target.name_field)
    later -= required
    conditions: dict[str, str] = {}
    for column in columns:
        if column.api_name == "not_duplicate_reason":
            conditions[column.api_name] = "Only if this End Client already has an open pursuit and this is a different project"
            continue
        shown_when = condition_in_words(column.visibility_condition, labels, directory, picklists)
        if shown_when:
            conditions[column.api_name] = condition_note(shown_when)

    filename = f"Astrikos ARK - {target.plural} import sample"
    if format == "csv":
        return _download(template_csv(columns, required), f"{filename}.csv", "text/csv; charset=utf-8")

    notes = []
    if target.stage_field:
        notes.append("New leads are imported at Stage 0 · Connect. Move them forward in ARK, where each move's checks are recorded.")
    if target.key == "partners":
        notes.append("Account Type must include a partner type, or the row won't appear on Partners.")
    body = template_workbook(
        plural=target.plural, noun=target.noun, columns=columns, required=required, later=later,
        conditions=conditions, directory=directory, notes=notes, generated=now_utc().date(),
    )
    return _download(body, f"{filename}.xlsx", XLSX)


@router.get("/spreadsheets/{module}/export")
def export(module: str, request: Request, db: Session = Depends(get_db)):
    target = _export_target(module, request, db)
    body = export_workbook(db, target, now_utc())
    return _download(body, export_filename(target.title, now_utc()), XLSX)


def _json_object(text: str | None) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


async def _import(module: str, request: Request, db: Session, user: User, *, commit: bool) -> dict:
    target = _import_target(module)
    filename = request.query_params.get("filename") or ""
    overrides = _json_object(request.query_params.get("mapping"))
    answers = {k: v for k, v in _json_object(request.query_params.get("answers")).items() if isinstance(v, dict)}
    data = await request.body()
    try:
        sheets = read_upload(filename, data)
        report = run_import(db, target, sheets, user=user, overrides=overrides, answers=answers, commit=commit)
    except FileRefusal as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, refusal("FILE_REFUSED", str(exc))) from None
    report["filename"] = filename
    report["checked_at"] = datetime.now().isoformat(timespec="seconds")
    return report


@router.post("/spreadsheets/{module}/import/preview")
async def preview_import(module: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return await _import(module, request, db, user, commit=False)


@router.post("/spreadsheets/{module}/import")
async def commit_import(module: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    report = await _import(module, request, db, user, commit=True)
    if not report["committed"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "IMPORT_NOT_READY",
                "Nothing was imported." if report["failed"] else "Nothing to import.",
                [f"{report['failed']} of {report['total']} rows need fixing. Check the file again to see them."] if report["failed"] else [],
                report=report,
            ),
        )
    return report

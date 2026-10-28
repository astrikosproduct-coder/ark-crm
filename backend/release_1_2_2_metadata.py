"""
v1.2.2 — the Alliance fields at Stage 0, and an "Other" payment milestone
(the head's asks, 28 Oct 2026).

    python release_1_2_2_metadata.py            # dry run: validates, writes nothing
    python release_1_2_2_metadata.py --apply    # change the register and publish

1. ALLIANCE FIELDS AT STAGE 0
   Alliance Structure, Pre-Bid Alliance Partner and PBAA Signed Date were asked at
   Stage 3 — Prescription, and Alliance Structure was shown on EVERY Lead (a Direct
   sale was asked who its alliance partner was). They now sit in Stage 0 — Connect,
   beside Customer (Partner / SI), and show ONLY when Deal Source is Partner-sourced.
   Opportunities and Deals read them through the Lead as before, with the same rule.

   What does NOT change: the stage each one is DEMANDED at (still the move out of
   Stage 3 — mandatory_from / blocks_transition untouched). Showing a field early is
   not the same as demanding it early: a Partner-sourced Lead already past Stage 0
   is not newly blocked. Pay-When-Paid keeps its own rule (Alliance Structure =
   Partner prime), so it appears once Alliance Structure is filled.

   Values already stored stay in their columns — on a Direct Lead too; they are only
   no longer shown. The run lists those Leads.

2. "OTHER" PAYMENT MILESTONE
   The eight standard milestones stay. A ninth choice, Other, lets the head name a
   milestone of their own (the row's Milestone Name box). See migration
   r12_0001_milestone_amount for the columns.

NO DDL here. Order on a server: dump -> alembic upgrade head -> this script
(dry run, then --apply) -> start the new code. Run on development AND production.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldPlacement, Lead, Picklist, PicklistValue, Section  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

NOTE = "v1.2.2: Alliance fields at Stage 0 for Partner-sourced deals; an Other payment milestone"

#: One rule for all three fields, on Leads and on what reads them through.
PARTNER_SOURCED = "deal_source == 'Partner-sourced'"

#: In the order they draw — directly after Customer (Partner / SI), which shows on
#: the same condition. Each takes the next place after it; the rest of Stage 0 moves
#: down to make room (see apply).
ALLIANCE = ["pre_bid_alliance_partner", "alliance_structure", "pbaa_signed_date"]
AFTER = "customer_partner_si"
MODULES = ("leads", "opportunities", "deals")

MILESTONE_LIST = "administration__milestone"
OTHER_KEY, OTHER_LABEL = "OTHER", "Other"


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def apply(db) -> list[str]:
    log: list[str] = []

    stage0 = db.scalars(
        select(Section).where(Section.module_key == "leads").where(Section.label.like("STAGE 0%"))
    ).first()
    if stage0 is None:
        raise SystemExit("Leads has no Stage 0 section — is this the ARK register?")

    # ---- 1. the Alliance fields
    lead_of = {}
    for api_name in ALLIANCE:
        lead = placement(db, "leads", api_name)
        if lead is None:
            raise SystemExit(f"leads.{api_name} is not placed — is this the ARK register?")
        lead_of[api_name] = lead
    after = placement(db, "leads", AFTER)
    if after is None or after.section_id != stage0.id:
        raise SystemExit(f"leads.{AFTER} is not in {stage0.label} — is this the ARK register?")

    # Directly after Customer (Partner / SI): one place each, the rest of Stage 0 down by three.
    wanted = {name: after.sort_order + 1 + i for i, name in enumerate(ALLIANCE)}
    if any(lead_of[name].sort_order != wanted[name] or lead_of[name].section_id != stage0.id for name in ALLIANCE):
        later = list(
            db.scalars(
                select(FieldPlacement)
                .where(FieldPlacement.module_key == "leads")
                .where(FieldPlacement.section_id == stage0.id)
                .where(FieldPlacement.status == "active")
                .where(FieldPlacement.sort_order > after.sort_order)
                .where(FieldPlacement.api_name.not_in(ALLIANCE))
            )
        )
        for p in later:
            p.sort_order += len(ALLIANCE)
        log.append(f"{stage0.label}: {len(later)} later field(s) move down {len(ALLIANCE)} places to make room")

    for api_name in ALLIANCE:
        lead = lead_of[api_name]
        if lead.section_id != stage0.id:
            was = db.get(Section, lead.section_id)
            lead.section_id = stage0.id
            log.append(f"leads.{api_name}: moved from {was.label if was else '?'} to {stage0.label}")
        if lead.sort_order != wanted[api_name]:
            lead.sort_order = wanted[api_name]
            log.append(f"leads.{api_name}: drawn directly after {AFTER}")
        # Drawn where Stage 0 asks it — the stage it is DEMANDED at is left alone.
        if lead.capture_stage != 0:
            lead.capture_stage = 0
            log.append(f"leads.{api_name}: captured at Stage 0 (still due at Stage {lead.mandatory_from})")
        for module in MODULES:
            p = placement(db, module, api_name)
            if p is not None and p.visibility_condition != PARTNER_SOURCED:
                p.visibility_condition = PARTNER_SOURCED
                log.append(f"{module}.{api_name}: shown only when Deal Source is Partner-sourced")

    # ---- 2. the Other milestone
    picklist = db.get(Picklist, MILESTONE_LIST)
    if picklist is None:
        raise SystemExit(f"{MILESTONE_LIST} is not a picklist — is this the ARK register?")
    values = list(db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == MILESTONE_LIST)))
    other = next((v for v in values if v.key == OTHER_KEY), None)
    if other is None:
        db.add(
            PicklistValue(
                picklist_key=MILESTONE_LIST,
                key=OTHER_KEY,
                label=OTHER_LABEL,
                sort_order=max((v.sort_order for v in values), default=0) + 1,
                active=True,
            )
        )
        log.append(f"{MILESTONE_LIST}: added '{OTHER_LABEL}' (a milestone the person names)")
    elif not other.active:
        other.active = True
        log.append(f"{MILESTONE_LIST}: '{OTHER_LABEL}' is offered again")
    return log


def report(db) -> None:
    """What the move leaves behind on live Leads — said, never changed."""
    hidden = db.execute(
        select(Lead.lead_id, Lead.opportunity_name, Lead.deal_source)
        .where(Lead.alliance_structure.is_not(None))
        .where((Lead.deal_source.is_(None)) | (Lead.deal_source != "PARTNER_SOURCED"))
    ).all()
    if hidden:
        print(f"\n{len(hidden)} Lead(s) hold an Alliance Structure but are not Partner-sourced "
              "(the value is kept, no longer shown):")
        for _, name, source in hidden[:15]:
            print(f"  {name}  (Deal Source: {source or 'blank'})")
    missing = db.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.deal_source == "PARTNER_SOURCED")
        .where(Lead.alliance_structure.is_(None))
    )
    print(f"\n{missing} Partner-sourced Lead(s) have no Alliance Structure yet — it shows on them from now, "
          "and is asked for when each leaves Stage 3.")


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    with SessionLocal() as db:
        log = apply(db)
        print(f"v1.2.2 register changes — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        report(db)
        if not log:
            db.rollback()
            return 0
        db.flush()
        if mode == "dry":
            validation = _validation_out(build_snapshot(db))
            print(f"\nValidation: {'ok' if validation.ok else 'FAILED'}")
            for error in validation.errors:
                print(f"  error: {error}")
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0 if validation.ok else 1
        try:
            result = _publish(db, build_snapshot(db), NOTE, None)
        except HTTPException as exc:
            db.rollback()
            print(f"\nNot published, nothing written: {exc.detail}")
            return 1
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}.")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

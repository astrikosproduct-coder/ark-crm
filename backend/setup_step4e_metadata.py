"""
Setup rebuild, 4e — make the register say what the record already does.

    python setup_step4e_metadata.py            # dry run: says what it would change
    python setup_step4e_metadata.py --apply    # change it and publish one version

Four changes, each turning something only code knew into a fact Setup shows:

1. An attached field lives in the section of the field it is attached to.
   Override Justification is drawn under Probability % in Health & Forecast,
   On Hold Reason and Closed Lost Reason under Status in Record State — but
   their section said Aging, so the layout editor showed them there and the
   record never did. Moved to where they draw; nothing on screen changes.

2. Required is Zoho's: a field is Required or not, and "Show only when…" says
   when it is on the form. Agreed 5 Oct 2026:
     * Conditional with no rule (60 fields) -> Optional. They are demanded of
       nobody today: a Conditional field with no rule never is.
     * Conditional with a rule -> Mandatory, keeping the rule. The rule was
       always the same as its "show when" rule, so it is demanded exactly when
       it is shown — as before.

3. The written formula sentence goes (agreed 5 Oct 2026). A field with a real
   formula has its readable version written from the formula itself now, so
   the sentence is dropped. A field with only a sentence — the two day
   counters the CRM works out, and fields of modules not built yet — keeps
   it at the end of its tooltip, so nothing that was said is lost.

4. Stage Skip Reason and Stage Reversal Reason are "asked at stage move"
   (migration 0043) — what spec/extensions.json's history_only listed.

Idempotent: a change already made is skipped. It stops if the draft has
other unpublished changes, because publishing would take them too.

DEPLOY ORDER: after `alembic upgrade` reaches 0043 and before the new code
starts; after setup_step4d_metadata.py. NO DDL — register rows only.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.metadata_spec import diff_snapshots  # noqa: E402
from app.models import FieldDefinition, FieldPlacement, Section  # noqa: E402
from app.routers.metadata import (  # noqa: E402
    _latest_version,
    _publish,
    _stage_of_section,
    _validation_out,
    build_snapshot,
)
from app.schemas_metadata import DESCRIPTION_MAX_LENGTH  # noqa: E402

NOTE = "Attached fields live where they draw; Required is a tick plus a rule; formula sentences into tooltips; stage-move reasons marked"

#: What spec/extensions.json stage_scoped.history_only held until this step.
STAGE_MOVE_REASONS = ("stage_skip_reason", "stage_reversal_reason")
PIPELINE = ("leads", "opportunities", "deals")


def plan(db) -> tuple[list[str], bool]:
    lines: list[str] = []
    stop = False
    active = list(db.scalars(select(FieldPlacement).where(FieldPlacement.status == "active")))
    by_name = {(p.module_key, p.scope_key, p.api_name): p for p in active}
    labels = {s.id: s.label for s in db.scalars(select(Section))}

    # 1 — attached fields into their anchor's section
    moved = 0
    for p in active:
        if not p.anchor_field:
            continue
        target = by_name.get((p.module_key, p.scope_key, p.anchor_field))
        if target is None or target.section_id == p.section_id:
            continue
        last = db.scalar(
            select(func.max(FieldPlacement.sort_order)).where(FieldPlacement.section_id == target.section_id)
        ) or 0
        lines.append(f"{p.module_key}.{p.api_name}: {labels[p.section_id]} -> {labels[target.section_id]} (under {p.anchor_field})")
        p.section_id = target.section_id
        p.capture_stage = _stage_of_section(labels[target.section_id])
        p.sort_order = last + 1
        moved += 1
    lines.append(f"attached fields moved to where they draw: {moved}")

    # 2 — Required is a tick plus a rule
    optional = mandatory = 0
    for p in active:
        if p.requirement != "Conditional":
            continue
        if not p.condition:
            p.requirement = "Optional"
            p.condition = None
            optional += 1
        elif p.visibility_condition and p.condition.strip() == p.visibility_condition.strip():
            p.requirement = "Mandatory"
            mandatory += 1
        else:
            lines.append(f"stop: {p.module_key}.{p.api_name} has a rule that differs from its show-when rule")
            stop = True
    lines.append(f"Conditional with no rule -> Optional: {optional}")
    lines.append(f"Conditional with a rule -> Required while shown: {mandatory}")

    # 3 — formula sentences
    dropped = kept = 0
    for d in db.scalars(select(FieldDefinition).where(FieldDefinition.computed_formula.is_not(None))):
        sentence = d.computed_formula.strip()
        if not d.computed_expr:
            tail = f" Worked out as: {sentence.rstrip('.')}."
            if sentence not in (d.description or ""):
                text = (d.description or "").rstrip()
                text = f"{text}{tail}" if text else tail.strip()
                if len(text) > DESCRIPTION_MAX_LENGTH:
                    lines.append(f"stop: {d.scope_key}.{d.api_name} tooltip would be {len(text)} characters")
                    stop = True
                    continue
                d.description = text
            kept += 1
        else:
            dropped += 1
        d.computed_formula = None
    lines.append(f"formula sentences dropped (written from the formula now): {dropped}")
    lines.append(f"formula sentences moved into the tooltip: {kept}")

    # 4 — asked at stage move
    marked = 0
    for p in active:
        if p.module_key in PIPELINE and p.api_name in STAGE_MOVE_REASONS and not p.asked_at_stage_move:
            p.asked_at_stage_move = True
            marked += 1
    lines.append(f"marked as asked at stage move: {marked}")
    return lines, stop


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        latest = _latest_version(db)
        pending = diff_snapshots(latest.snapshot, build_snapshot(db)) if latest else ["never published"]
        if pending:
            print("Stopped: the draft has unpublished changes, and publishing would take them too.")
            for line in pending[:20]:
                print(f"  {line}")
            print("Publish or undo them in Setup first, then run this again.")
            return 1

        lines, stop = plan(db)
        print(f"Setup 4e register changes — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for line in lines:
            print(f"  {line}")
        if stop:
            db.rollback()
            print("\nStopped — nothing written.")
            return 1
        db.flush()
        if not diff_snapshots(latest.snapshot, build_snapshot(db)):
            db.rollback()
            print("\nNothing to change.")
            return 0
        if not apply:
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

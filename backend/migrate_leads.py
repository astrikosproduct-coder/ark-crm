"""
One-time migration: frontend/spec/seed/leads.json -> PostgreSQL.

Run:  python migrate_leads.py            # dry run
      python migrate_leads.py --apply

Same shape as migrate_contacts.py: rename the seed's keys to register
api_names (extensions.json seed_normalisation.leads), then resolve every
picklist value to its KEY, with the same leading-code fallback contacts needed
("3" for "3_PRESCRIPTION", same idea as "DECM" for DECM_DECISION_MAKER).

Two things this file needs that accounts/contacts did not:

1. Date rebasing. spec/seed/_anchor.json fixes the day the seed was written
   against; src/lib/spec/seed.ts shifts every seed date by `today - anchor`
   in the browser so a demo opened months later still looks like a live
   pipeline. Reproduced here the same way, over the raw row before any other
   normalisation, so a migrated Lead's dates match what the browser would
   have shown on the same day.

2. The pipeline split. spec/module_split.json says Leads only owns Stages
   0-3; Stages 4-6 belong to Opportunities. LEAD-00119 (Stage 4) and
   LEAD-00122 (Stage 6) in the seed are past that boundary — the frontend
   normally reacts by freezing them to Stage 3 and deriving a matching
   Opportunity (see lib/spec/pipelineSeed.ts::deriveOpportunitiesFromLeads).
   Per the Phase-1 cutover decision, this script does NOT reproduce that
   derivation — Opportunities starts empty in Postgres — so a seed row past
   the Leads range is simply skipped, not migrated in any form.

expected_close_month is a further wrinkle: the seed writes it "yyyy-MM" (a
workbook shorthand — see extensions.json seed_normalisation.leads' note), but
the column is a real DATE. Coerced to the first of that month; the live UI
only ever sends a full date (Input type="date"), so this only matters for the
one-time seed load, never for a value a real user enters afterwards.

Idempotent: a lead whose id already exists is left untouched.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import Account, Contact, Lead, LeadDemoAttendee, LeadFeatureGap, User
from app.schemas import LEAD_LOOKUPS, LEAD_SCALARS

SPEC = Path(__file__).resolve().parent.parent / "frontend" / "spec"

Base.metadata.create_all(bind=engine)

DEMO_ATTENDEE_ROW_COLUMNS = ("attendee", "job_title", "organisation", "attendee_role")
FEATURE_GAP_ROW_COLUMNS = ("gap_description", "suite_module", "impact", "raised_by")

_MODELS_BY_COLLECTION = {"accounts": Account, "users": User, "contacts": Contact, "leads": Lead}

_ISO_DATE = None  # set in main(), compiled once
_ISO_MONTH = None


def slug(value: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(value).lower()).strip("-")


def build_resolver():
    fields = json.loads((SPEC / "fields.json").read_text(encoding="utf-8"))
    picklists = json.loads((SPEC / "picklists.json").read_text(encoding="utf-8"))
    extensions = json.loads((SPEC / "extensions.json").read_text(encoding="utf-8"))

    rename = extensions["seed_normalisation"]["leads"].get("rename", {})
    overrides = extensions.get("fields", {})

    resolvers = {}
    date_fields = set()
    for field in fields:
        if field.get("module") != "leads":
            continue

        # extensions.json's type_override wins, same as the frontend's spec
        # loader. secondary_sap_suites and suite_demonstrated are multiselect/
        # lookup in the register but frozen to free text for Phase 1 (Products
        # is a Round-5 table), so they must NOT be picklist-resolved here.
        api_name = field["api_name"]
        field_type = overrides.get(f"leads.{api_name}", {}).get("type_override") or field.get("type")

        if field_type == "date":
            date_fields.add(api_name)
        if field_type not in ("picklist", "multiselect"):
            continue

        table = {}
        for option in picklists.get(field.get("picklist")) or []:
            key = option["key"]
            table[slug(key)] = key
            table[slug(option["label"])] = key
            # "3" for "3_PRESCRIPTION" — project_stage is seeded as a bare
            # integer, same convention as contacts' role codes.
            table.setdefault(slug(key.split("_")[0]), key)

        resolvers[field["api_name"]] = table

    return rename, resolvers, date_fields


def normalise(row, rename, resolvers):
    out = {rename.get(k, k): v for k, v in row.items()}

    unresolved = []
    for api_name, table in resolvers.items():
        value = out.get(api_name)
        if value in (None, "", []):
            continue
        key = table.get(slug(value))
        if key is None and isinstance(value, str) and " " in value:
            # "GCC USD" / "UAE AED" -> USD / AED. The register's currency
            # picklist is bare ISO codes; the seed prefixes a region label.
            # Same shorthand idea as contacts' leading-code fallback (DECM),
            # just on the trailing word instead of the leading one.
            key = table.get(slug(value.split()[-1]))
        if key is None:
            unresolved.append(f"{api_name}={value!r}")
            key = value
        out[api_name] = key

    return out, unresolved


# --------------------------------------------------------------- date rebase


def _shift_date_string(value: str, delta: int) -> str | None:
    m = _ISO_DATE.match(value)
    if m:
        shifted = date.fromisoformat(m.group(1)) + timedelta(days=delta)
        return shifted.isoformat() + (m.group(2) or "")

    m = _ISO_MONTH.match(value)
    if m:
        shifted = date(int(m.group(1)), int(m.group(2)), 1) + timedelta(days=delta)
        return f"{shifted.year:04d}-{shifted.month:02d}"

    return None


def rebase(value, delta: int):
    """Deep-shift every ISO date/month string by `delta` days. Mirrors
    src/lib/spec/seed.ts's rebase(). Non-date strings pass through untouched."""
    if isinstance(value, str):
        return _shift_date_string(value, delta) or value
    if isinstance(value, list):
        return [rebase(v, delta) for v in value]
    if isinstance(value, dict):
        return {k: rebase(v, delta) for k, v in value.items()}
    return value


def _flatten(value):
    """A frozen multiselect (secondary_sap_suites) still carries a list in the
    seed, but its column is free text now — see extensions.json's
    type_override. Every Lead scalar column is a scalar, so a list can only
    mean this."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def _to_date(value, date_fields, api_name):
    """yyyy-MM or yyyy-MM-dd (already rebased) -> a real date for the column."""
    if api_name not in date_fields or not isinstance(value, str):
        return value
    m = _ISO_MONTH.match(value)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = _ISO_DATE.match(value)
    if m:
        return date.fromisoformat(m.group(1))
    return value


def main(apply: bool) -> None:
    import re

    global _ISO_DATE, _ISO_MONTH
    _ISO_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})([T ].*)?$")
    _ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")

    rename, resolvers, date_fields = build_resolver()
    seed = json.loads((SPEC / "seed" / "leads.json").read_text(encoding="utf-8"))
    module_split = json.loads((SPEC / "module_split.json").read_text(encoding="utf-8"))
    leads_upper_stage = module_split["ranges"]["leads"][1]

    anchor = json.loads((SPEC / "seed" / "_anchor.json").read_text(encoding="utf-8"))
    delta = (date.today() - date.fromisoformat(anchor["anchor_date"])).days

    db = SessionLocal()
    try:
        created = skipped = out_of_range = dangling_skipped = 0
        problems = []
        all_dangling = []

        for raw_unshifted in seed:
            lead_id = raw_unshifted.get("id")
            raw_stage = raw_unshifted.get("project_stage")

            # Past the Leads/Opportunities split boundary. Per the Phase-1
            # cutover decision, not migrated in any form — Opportunities
            # starts empty rather than reproducing the seed-time derivation.
            if isinstance(raw_stage, int) and raw_stage > leads_upper_stage:
                print(f"  {lead_id}  SKIPPED — stage {raw_stage} is past Leads' range (0-{leads_upper_stage})")
                out_of_range += 1
                continue

            raw = rebase(raw_unshifted, delta)
            row, unresolved = normalise(raw, rename, resolvers)
            problems.extend(f"{lead_id}: {u}" for u in unresolved)

            # Per-row, not all-or-nothing: a Lead naming an Account/User/
            # Contact that isn't in the DB is skipped on its own rather than
            # blocking every other row (confirmed with the user for
            # LEAD-00121 -> ACC-013, a genuinely missing seed Account).
            row_dangling = [
                f"{lead_id}: {field} {row.get(field)} not in DB"
                for field, collection in LEAD_LOOKUPS.items()
                if row.get(field) and db.get(_MODELS_BY_COLLECTION[collection], row.get(field)) is None
            ]
            if row_dangling:
                all_dangling.extend(row_dangling)
                dangling_skipped += 1
                continue

            if db.get(Lead, lead_id) is not None:
                skipped += 1
                continue

            print(
                f"  {lead_id}  {row.get('opportunity_name'):40} "
                f"stage={row.get('project_stage')} end_client={row.get('end_client')} "
                f"bd_owner={row.get('bd_owner')}"
            )

            if apply:
                lead = Lead(lead_id=lead_id)
                for name in LEAD_SCALARS:
                    if name in row:
                        setattr(lead, name, _flatten(_to_date(row[name], date_fields, name)))
                db.add(lead)
                db.flush()

                for order, attendee_row in enumerate(row.get("demo_attendees") or []):
                    db.add(
                        LeadDemoAttendee(
                            lead_id=lead_id,
                            row_order=order,
                            **{c: attendee_row.get(c) for c in DEMO_ATTENDEE_ROW_COLUMNS},
                        )
                    )
                for order, gap_row in enumerate(row.get("feature_gaps_logged") or []):
                    db.add(
                        LeadFeatureGap(
                            lead_id=lead_id,
                            row_order=order,
                            **{c: gap_row.get(c) for c in FEATURE_GAP_ROW_COLUMNS},
                        )
                    )

            created += 1

        if problems:
            print("\nPicklist values that would not resolve (stored as-is):")
            for p in problems:
                print(f"  ! {p}")

        if all_dangling:
            print("\nBROKEN LINKS - Lead skipped, not migrated:")
            for d in all_dangling:
                print(f"  !! {d}")

        if apply:
            db.commit()
            print(
                f"\nApplied. {created} created, {skipped} already present, "
                f"{out_of_range} skipped (out of Leads' stage range), "
                f"{dangling_skipped} skipped (broken link)."
            )
        else:
            print(
                f"\nDry run. {created} would be created, {skipped} already present, "
                f"{out_of_range} would be skipped (out of Leads' stage range), "
                f"{dangling_skipped} would be skipped (broken link)."
            )
            print("Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)

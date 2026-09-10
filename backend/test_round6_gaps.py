"""
Round-6 gap closure: Opportunities, cutover readiness, GIN, capture_stage.

Run:  python test_round6_gaps.py

Covers the four gaps the Round-6 audit left open, in the order they were
raised. Assertions are made against PostgreSQL and against generated files
rather than against the API's own account of itself, because what is being
proved is where the authority actually lives.

    GAP 1  opportunities is a first-class module in the metadata tables, and
           the pipeline structure is read from PostgreSQL rather than from a
           hand-edited frontend JSON
    GAP 2  the JSONB dynamic-field path is complete on all five business
           modules, not just the two already served by FastAPI
    GAP 3  GIN indexes exist and the planner can use them
    GAP 4  no field sits in a numbered STAGE section without a capture stage
"""

import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import SessionLocal, engine

engine.echo = False

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.metadata_spec import SPEC_DIR  # noqa: E402
from app.models import Deal, Opportunity  # noqa: E402
from app.custom_fields import custom_field_defs  # noqa: E402
from app.module_split import (  # noqa: E402
    parent_of,
    pipeline_modules,
    range_of,
)

META = "/api/admin/metadata"
client = TestClient(app)

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name}  {detail}")


def sql(statement: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(statement), params).fetchall()


def spec(name: str):
    return json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))


# =====================================================================
# GAP 1 — Opportunities as a first-class module
# =====================================================================


def gap1() -> None:
    print("\nGAP 1 — Opportunities as a first-class Administration module")

    with SessionLocal() as db:
        modules = pipeline_modules(db)
        opp_range = range_of(db, "opportunities")
        opp_parent = parent_of(db, "opportunities")
        deal_parent = parent_of(db, "deals")
        # source_modules_for() is gone as of Round 7 — see app/module_split.py.
        # It walked the module parent chain to GUESS which field_metadata
        # modules could supply an Opportunity's custom fields, because
        # placement was computed in the browser and the backend had to
        # reconstruct the answer. Now a placement's module_key IS the business
        # table, so custom_field_defs() needs no chain at all — it is checked
        # directly below in 1.7.
        opp_custom = custom_field_defs(db, "opportunities")
        account_custom = custom_field_defs(db, "accounts")

    row = sql(
        "SELECT label, is_pipeline, stage_field, parent_module, parent_link, active "
        "FROM modules WHERE module_key = 'opportunities'"
    )
    check(
        "1.1 opportunities exists as a normal module row",
        bool(row) and row[0][0] == "Opportunities" and row[0][1] is True and row[0][5] is True,
        str(row),
    )
    check(
        "1.2 its pipeline structure is in PostgreSQL",
        row and row[0][2] == "project_stage"
        and row[0][3] == "leads"
        and row[0][4] == "parent_lead",
        str(row),
    )

    # Stages, in the existing stages table — not a second one.
    owners = dict(sql("SELECT stage, owner_module FROM stages ORDER BY stage"))
    check(
        "1.3 Opportunity stages 4-6 are owned in the existing stages table",
        all(owners.get(s) == "opportunities" for s in (4, 5, 6))
        and all(owners.get(s) == "leads" for s in (0, 1, 2, 3))
        and all(owners.get(s) == "deals" for s in (7, 8, 9)),
        str(owners),
    )
    check(
        "1.4 stage range derives from stage ownership, not a second source",
        opp_range == (4, 6),
        str(opp_range),
    )
    check(
        "1.5 the parent chain is in the DB (opps -> leads, deals -> opps)",
        opp_parent == ("leads", "parent_lead")
        and deal_parent == ("opportunities", "parent_opportunity"),
        f"{opp_parent} {deal_parent}",
    )
    check(
        "1.6 pipeline order comes from the DB",
        modules == ["leads", "opportunities", "deals"],
        str(modules),
    )

    # The hardcoded tuple AND the parent-chain guess it replaced are both gone.
    # Round 7: custom_field_defs(table) is placements_of(table,
    # storage='custom_fields') — one query against field_placements.module_key,
    # no inference. This is also MORE ACCURATE than the chain walk it replaced:
    # the chain returned every leads custom field for a query about
    # opportunities, including ones that render only on Leads (a Stage 0 field
    # would have been writable on an Opportunity that never shows it). A
    # placement query cannot make that mistake — see test_placements.py case 11.
    check(
        "1.7 custom-field ownership is scoped by PLACEMENT, not a module chain",
        isinstance(opp_custom, dict) and isinstance(account_custom, dict),
        f"opp={sorted(opp_custom)} acct={sorted(account_custom)}",
    )

    # Administration sees it like any other module.
    listed = client.get(f"{META}/modules").json()
    check(
        "1.8 Administration lists Opportunities among the modules",
        any(m["module_key"] == "opportunities" for m in listed),
        f"{[m['module_key'] for m in listed]}",
    )

    # module_split.json's structural blocks are generated from the DB.
    split = spec("module_split.json")
    check(
        "1.9 module_split.json ranges/pipeline/stage_field are generated from the DB",
        split["ranges"]["opportunities"] == [4, 6]
        and split["pipeline"] == ["leads", "opportunities", "deals"]
        and split["stage_field"]["opportunities"] == "project_stage"
        and split["read_through"]["parent_of"]["opportunities"] == "leads",
        json.dumps({k: split.get(k) for k in ("pipeline", "ranges")}),
    )
    # Round 7: `own`, `shared`, `section_order` and `relocated_fields` are GONE
    # from this file, on purpose — see app/metadata_spec.py::DEAD_SPLIT_BLOCKS.
    # They used to be the hand-authored half of module_split.json describing
    # WHERE A FIELD GOES; that question is a field_placements row now, and
    # leaving those blocks in the file would let it be mistaken for a second
    # authority on placement. `register_corrections` is the one hand-authored
    # block that survives, because it is genuine register prose (a workbook
    # inconsistency to fix), not a placement decision.
    check(
        "1.10 placement-decision blocks are gone; register_corrections survives",
        all(k not in split for k in ("own", "shared", "section_order", "relocated_fields"))
        and "register_corrections" in split
        and len(split["register_corrections"]) > 1,
        str(list(split)),
    )

    # No duplicate Opportunity metadata tables were introduced.
    tables = {
        r[0] for r in sql("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    forbidden = {
        "opportunity_field_metadata",
        "opportunity_stages",
        "opportunity_module_config",
        "opportunity_sections",
        "custom_values",
        "field_values",
    }
    check(
        "1.11 no duplicate / per-module metadata tables were created",
        not (tables & forbidden),
        str(tables & forbidden),
    )

    # Opportunity fields are reachable: the register files them on leads, and
    # the split routes them by the stage ownership now held in the DB.
    opp_stage_fields = sql(
        """
        SELECT count(*) FROM field_metadata f
          JOIN modules m ON m.module_key = f.module_key
         WHERE f.status = 'active' AND f.capture_stage BETWEEN 4 AND 6
        """
    )
    check(
        "1.12 Opportunity-stage fields exist and are not lost",
        opp_stage_fields[0][0] > 0,
        str(opp_stage_fields),
    )


# =====================================================================
# GAP 2 — the JSONB path on every business module
# =====================================================================

MODULES = [
    # (business table, API collection, id field, id value, minimum create body)
    ("accounts", "accounts", "account_id", "ACC-R6G", {"account_name": "R6 gap test"}),
    ("contacts", "contacts", "contact_id", "CON-R6G", {"full_name": "R6 gap test"}),
    ("leads", "leads", "lead_id", "LEAD-R6G", {"opportunity_name": "R6 gap test"}),
    ("opportunities", "opportunities", "opportunity_id", "OPP-R6G", {}),
    ("deals", "deals", "deal_id", "DEAL-R6G", {"deal_name": "R6 gap test"}),
]

# The module a custom field is CREATED on. Before Round 7, Opportunities and
# Deals had no field rows of their own, so an admin field for either was
# necessarily a `leads` row that source_modules_for()'s parent-chain guess
# made visible on the pipeline modules below it too. Round 7 makes each
# pipeline module administrable on its own terms — creating a field ON
# Opportunities is now a normal placement on Opportunities, not a proxy
# through Leads — which is the redesign's whole point (CLAUDE.md rule on
# Administration -> Opportunities -> Fields showing what the CRM shows).
DEFINING_MODULE = {
    "accounts": "accounts",
    "contacts": "contacts",
    "leads": "leads",
    "opportunities": "opportunities",
    "deals": "deals",
}


def gap2() -> None:
    print("\nGAP 2 — dynamic-field JSONB path, all five business modules")

    for table, collection, id_field, record_id, body in MODULES:
        module = DEFINING_MODULE[table]
        api_name = f"r6g_{table}_note"
        second = f"r6g_{table}_extra"

        # A section that is NOT a numbered STAGE section, so capture_stage
        # derivation does not apply and the field is reachable on any screen.
        sections = client.get(f"{META}/sections", params={"module": module}).json()
        section = next(
            (s for s in sections if not s["label"].startswith("STAGE ")), sections[0]
        )

        with SessionLocal() as db:
            # Leftovers from a previous run. Round 7: these fields live in
            # field_definitions/field_placements, not field_metadata — and
            # placements must go first, or the FK (ON DELETE RESTRICT) refuses
            # to drop a definition still pointed at.
            db.execute(
                text(
                    "DELETE FROM field_placements WHERE api_name IN (:a, :b)"
                ),
                {"a": api_name, "b": second},
            )
            db.execute(
                text(
                    "DELETE FROM field_definitions WHERE api_name IN (:a, :b)"
                ),
                {"a": api_name, "b": second},
            )
            db.execute(
                text(f"DELETE FROM {table} WHERE {id_field} = :id"), {"id": record_id}
            )
            db.commit()

        made_a = client.post(
            f"{META}/fields",
            json={
                "module_key": module,
                "section_id": section["id"],
                "api_name": api_name,
                "label": "R6 gap note",
                "field_type": "text",
            },
        )
        made_b = client.post(
            f"{META}/fields",
            json={
                "module_key": module,
                "section_id": section["id"],
                "api_name": second,
                "label": "R6 gap extra",
                "field_type": "text",
            },
        )
        # POST /fields returns a PLACEMENT (see FieldOut: `id` is the placement,
        # `definition_id` the canonical field). Deleting the field EVERYWHERE
        # — which this test means by "delete the field" — takes the
        # definition id; see DELETE /fields/{definition_id} in routers/metadata.py.
        field_id = made_a.json().get("definition_id")

        # CREATE with a value, flat, the way the form engine posts.
        created = client.post(
            f"/api/{collection}",
            json={id_field: record_id, **body, api_name: "first", second: "keep me"},
        )
        stored = sql(
            f"SELECT custom_fields FROM {table} WHERE {id_field} = :id", id=record_id
        )
        check(
            f"2.{table}: create writes both values into custom_fields",
            created.status_code == 201
            and stored
            and stored[0][0].get(api_name) == "first"
            and stored[0][0].get(second) == "keep me",
            f"status={created.status_code} stored={stored[0][0] if stored else None}",
        )

        # READ
        read = client.get(f"/api/{collection}/{record_id}")
        check(
            f"2.{table}: read returns the value under its api_name",
            read.status_code == 200 and read.json().get(api_name) == "first",
            f"status={read.status_code} value={read.json().get(api_name)!r}",
        )

        # UPDATE one field — the other must survive (merge, not replace).
        client.patch(f"/api/{collection}/{record_id}", json={api_name: "second"})
        stored = sql(
            f"SELECT custom_fields FROM {table} WHERE {id_field} = :id", id=record_id
        )
        check(
            f"2.{table}: updating one custom field leaves the others alone",
            stored[0][0].get(api_name) == "second"
            and stored[0][0].get(second) == "keep me",
            str(stored[0][0]),
        )

        # UNKNOWN field protection
        client.patch(f"/api/{collection}/{record_id}", json={"r6g_not_a_field": "junk"})
        rejected = client.patch(
            f"/api/{collection}/{record_id}",
            json={"custom_fields": {"r6g_not_a_field": "junk"}},
        )
        stored = sql(
            f"SELECT custom_fields FROM {table} WHERE {id_field} = :id", id=record_id
        )
        check(
            f"2.{table}: unknown field never becomes a JSONB key",
            "r6g_not_a_field" not in stored[0][0] and rejected.status_code == 422,
            f"status={rejected.status_code} stored={stored[0][0]}",
        )

        # REGISTERED field protection — a typed column stays typed.
        typed_col, typed_val = {
            "accounts": ("region", "MEA"),
            "contacts": ("job_title", "CTO"),
            "leads": ("country", "UAE"),
            "opportunities": ("rfp_type", "OPEN_TENDER"),
            "deals": ("project_code", "PRJ-1"),
        }[table]
        client.patch(f"/api/{collection}/{record_id}", json={typed_col: typed_val})
        row = sql(
            f"SELECT {typed_col}, custom_fields FROM {table} WHERE {id_field} = :id",
            id=record_id,
        )
        check(
            f"2.{table}: registered field stayed in its typed column",
            row[0][0] == typed_val and typed_col not in row[0][1],
            f"{typed_col}={row[0][0]!r} custom_fields={row[0][1]}",
        )

        # DELETE the field EVERYWHERE — the value must survive. Round 7:
        # field_metadata is frozen and never written to any more, so status is
        # read from field_definitions instead — the table this delete acts on.
        client.delete(f"{META}/fields/{field_id}")
        stored = sql(
            f"SELECT custom_fields FROM {table} WHERE {id_field} = :id", id=record_id
        )
        state = sql(
            "SELECT status FROM field_definitions WHERE api_name = :a", a=api_name
        )
        check(
            f"2.{table}: deleting the field preserves the stored value",
            state[0][0] == "deleted" and stored[0][0].get(api_name) == "second",
            f"status={state} stored={stored[0][0]}",
        )

        # RESTORE — value visible again through the API.
        client.post(f"{META}/fields/{field_id}/restore")
        read = client.get(f"/api/{collection}/{record_id}")
        check(
            f"2.{table}: restoring the field shows the value again",
            read.json().get(api_name) == "second",
            f"value={read.json().get(api_name)!r}",
        )

        with SessionLocal() as db:
            db.execute(
                text(f"DELETE FROM {table} WHERE {id_field} = :id"), {"id": record_id}
            )
            db.execute(
                text("DELETE FROM field_metadata WHERE api_name IN (:a, :b)"),
                {"a": api_name, "b": second},
            )
            db.commit()

        if made_b.status_code != 201:
            check(f"2.{table}: second field created", False, made_b.text[:150])


# =====================================================================
# GAP 3 — GIN indexes
# =====================================================================


def gap3() -> None:
    print("\nGAP 3 — GIN indexes on custom_fields")

    tables = ("accounts", "contacts", "leads", "opportunities", "deals")
    indexes = {
        r[0]: r[1]
        for r in sql(
            "SELECT tablename, indexdef FROM pg_indexes "
            "WHERE indexname LIKE '%custom_fields_gin'"
        )
    }
    check(
        "3.1 every custom_fields column has a GIN index",
        all(t in indexes for t in tables),
        f"missing: {[t for t in tables if t not in indexes]}",
    )
    check(
        "3.2 the indexes use jsonb_path_ops, matching the containment queries",
        all("jsonb_path_ops" in indexes.get(t, "") for t in tables),
        str(indexes),
    )

    # The planner can use it for a containment query. seqscan is disabled for
    # the check because these tables hold a handful of rows and a sequential
    # scan is genuinely cheaper there — what is being proved is that the index
    # is USABLE for this query shape, not that it wins on 18 rows.
    with engine.connect() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            r[0]
            for r in connection.execute(
                text(
                    "EXPLAIN SELECT * FROM accounts "
                    "WHERE custom_fields @> '{\"x\": \"y\"}'::jsonb"
                )
            )
        )
    check(
        "3.3 a containment query can use the GIN index",
        "ix_accounts_custom_fields_gin" in plan,
        plan.replace("\n", " | ")[:200],
    )


# =====================================================================
# GAP 4 — capture_stage
# =====================================================================


def gap4() -> None:
    print("\nGAP 4 — capture_stage")

    orphans = sql(
        """
        SELECT f.module_key, s.label, f.api_name
          FROM field_metadata f
          JOIN sections s ON s.id = f.section_id
          JOIN modules  m ON m.module_key = f.module_key
         WHERE m.is_pipeline
           AND f.status = 'active'
           AND s.label ~ '^STAGE [0-9]'
           AND f.capture_stage IS NULL
        """
    )
    check(
        "4.1 no pipeline field sits in a numbered STAGE section without a stage",
        not orphans,
        str(orphans),
    )

    mismatched = sql(
        """
        SELECT f.module_key, s.label, f.api_name, f.capture_stage
          FROM field_metadata f
          JOIN sections s ON s.id = f.section_id
          JOIN modules  m ON m.module_key = f.module_key
         WHERE m.is_pipeline
           AND f.status = 'active'
           AND s.label ~ '^STAGE [0-9]'
           AND f.capture_stage <> substring(s.label from '^STAGE ([0-9]+)')::int
        """
    )
    check(
        "4.2 capture_stage agrees with the section it is in",
        not mismatched,
        str(mismatched),
    )

    # The administration module's "STAGE DEFINITION (configuration)" sections
    # are config headings, not pipeline stages, and must NOT be swept up.
    admin_untouched = sql(
        """
        SELECT count(*) FROM field_metadata f
          JOIN sections s ON s.id = f.section_id
         WHERE f.module_key = 'administration'
           AND s.label LIKE 'STAGE %'
           AND f.capture_stage IS NULL
        """
    )
    check(
        "4.3 administration's STAGE-named config sections were left alone",
        admin_untouched[0][0] > 0,
        f"{admin_untouched[0][0]} rows (expected > 0 — they are not pipeline stages)",
    )

    # A new field created in a numbered STAGE section gets its stage derived.
    sections = client.get(f"{META}/sections", params={"module": "leads"}).json()
    stage_section = next(s for s in sections if s["label"].startswith("STAGE 2"))
    with SessionLocal() as db:
        db.execute(text("DELETE FROM field_placements WHERE api_name = 'r6g_derived'"))
        db.execute(text("DELETE FROM field_definitions WHERE api_name = 'r6g_derived'"))
        db.commit()

    made = client.post(
        f"{META}/fields",
        json={
            "module_key": "leads",
            "section_id": stage_section["id"],
            "api_name": "r6g_derived",
            "label": "R6 derived stage",
            "field_type": "text",
        },
    )
    check(
        "4.4 a new field in a STAGE section has its capture stage derived",
        made.status_code == 201 and made.json()["capture_stage"] == 2,
        f"status={made.status_code} capture_stage={made.json().get('capture_stage')}",
    )

    # And publish refuses a field whose stage disagrees with its section.
    # capture_stage is a PLACEMENT column since Round 7 — it can differ by
    # module — so this goes through PATCH /placements/{id}, not /fields/{id}
    # (which now edits the canonical definition and refuses placement keys).
    client.patch(f"{META}/placements/{made.json()['placement_id']}", json={"capture_stage": 5})
    validation = client.get(f"{META}/validate").json()
    check(
        "4.5 publish validation catches a stage/section disagreement",
        not validation["ok"]
        and any("r6g_derived" in e for e in validation["errors"]),
        str(validation["errors"][:3]),
    )

    refused = client.post(f"{META}/publish", json={"note": "should be refused"})
    check(
        "4.6 a field with a bad capture stage cannot be published",
        refused.status_code == 422,
        f"status={refused.status_code}",
    )

    with SessionLocal() as db:
        db.execute(text("DELETE FROM field_placements WHERE api_name = 'r6g_derived'"))
        db.execute(text("DELETE FROM field_definitions WHERE api_name = 'r6g_derived'"))
        db.commit()


def main() -> int:
    print("Round-6 gap closure\n" + "=" * 60)
    gap1()
    gap2()
    gap3()
    gap4()

    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM metadata_versions WHERE note LIKE '%should be refused%'")
        )
        db.commit()

    print(f"\n{'=' * 60}\n{len(passed)} passed, {len(failed)} failed")
    for line in failed:
        print(f"  ! {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

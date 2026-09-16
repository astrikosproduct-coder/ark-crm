"""
Round 7 — the field placement model, tested against the real database.

    python test_placements.py

Covers the real-field cases section 30 of the brief names, plus the schema
integrity rules and the architectural constraints the design depends on.
Assertions are made against PostgreSQL and against the resolver rather than
against the API's account of itself, because what is being proved is where the
authority actually lives.

    1   no duplicate field definitions
    2   Administration shows what the CRM renders
    3   one_time_revenue        one definition, two placements, D1 behaviour
    4   project_stage           relabelled, and absent from Deals
    5   probability_pct         three independent owned values
    6   progression_pct         D4 — plain editable Number
    7   lead_status             placement label overrides
    8   end_client              D3 — Deal owns; scope keeps Partners/Quotes apart
    9   read-through            stores nothing, not editable, resolves to parent
    10  shared field            one definition, explicit modes per placement
    11  admin-created field     one definition, one placement, custom_fields
    12  CARRY-FORWARD, LIVE     real records: seeded, then diverging
    13  delete / restore        placement vs definition, and the cascade flag
    14  database integrity      the constraints refuse what they must
    15  architecture            no second projection, no dynamic DDL
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import ast  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

# This test writes. Refuse to run against the database the prototype is
# demonstrated from — the copy is made by run_tests.py. See test_db.py.
require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app import carry_forward  # noqa: E402
from app import metadata_resolver as R  # noqa: E402
from app.custom_fields import custom_field_defs  # noqa: E402
from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402
from app.models import (  # noqa: E402
    Deal,
    FieldDefinition,
    FieldPlacement,
    Lead,
    Opportunity,
)

client = TestClient(app)

# Every route is mounted behind require_access / require_admin, which read a
# signed-in user from the session cookie. A TestClient has none and cannot get
# one — sign-in goes through Entra. Without this, every request here returns
# 401 and the suite asserts nothing. See test_support.py.
sign_in_as_admin(app)


PASSED = 0
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


def head(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# =====================================================================
def case_1_no_duplicates(db) -> None:
    head("1  no duplicate field definitions")

    rows = db.execute(
        text(
            "SELECT scope_key, api_name, count(*) FROM field_definitions "
            "GROUP BY scope_key, api_name HAVING count(*) > 1"
        )
    ).all()
    check("no two definitions share (scope_key, api_name)", not rows, str(rows))

    # The brief's non-negotiable: One-Time Revenue must not exist once per
    # module. Three modules, one definition.
    rows = db.execute(
        text(
            "SELECT count(*) FROM field_definitions WHERE api_name = 'one_time_revenue' "
            "AND scope_key = 'pipeline'"
        )
    ).scalar()
    check("exactly one pipeline definition of one_time_revenue", rows == 1, f"got {rows}")

    orphans = db.execute(
        text(
            "SELECT count(*) FROM field_placements p "
            "LEFT JOIN field_definitions d ON d.id = p.definition_id "
            "WHERE d.id IS NULL"
        )
    ).scalar()
    check("no orphan placements", orphans == 0, f"got {orphans}")

    drift = db.execute(
        text(
            "SELECT count(*) FROM field_placements p "
            "JOIN field_definitions d ON d.id = p.definition_id "
            "WHERE d.api_name <> p.api_name"
        )
    ).scalar()
    check("no placement api_name drifted from its definition", drift == 0, f"got {drift}")


# =====================================================================
def case_2_administration_sees_the_crm(db) -> None:
    head("2  Administration shows what the CRM renders")

    # leads was 81 until Close Date Pushback Count was deleted from the
    # register (close_month_record_state.py). Opportunities and Deals were
    # unchanged at 105 and 97: each lost that same field and gained its own
    # instance of Expected Close Month in the same change.
    #
    # Pursuit Groups (pursuit_group_metadata.py, 13 Sep 2026): Opportunities and
    # Deals each gain is_primary_pursuit, pursuit_group and a read-through
    # fx_rate_at_entry (+3). Leads gains pursuit_group and not_duplicate_reason
    # and loses parent_pursuit (+1) — 80 assumed a leads count of 80 that the
    # register had already left at 79 before this change.
    # Opportunities 108 -> 107: rfp_document_file was deleted in Administration
    # on 15 Sep 2026 (version 109), deliberately — see case 11.
    # Deals 100 -> 98: created_by_date and modified_by_date were retired on
    # 16 Sep 2026 (deal_register_alignment.py, after migration 0030). They were
    # the Deals sheet's own names for created_date and modified_date, which the
    # module also placed — six system rows for four facts, four of them blank
    # because the columns behind them were the other two.
    for module, expected in (("leads", 80), ("opportunities", 107), ("deals", 98)):
        resolved = len(R.resolved_fields(db, module))
        api = client.get(
            "/api/admin/metadata/fields", params={"module": module}
        )
        listed = len(api.json()) if api.status_code == 200 else -1
        check(
            f"{module}: resolver {resolved} == Administration API {listed} == {expected}",
            resolved == listed == expected,
            f"resolver={resolved} api={listed} status={api.status_code}",
        )

    # The headline defect: Opportunities used to list zero.
    names = {f["api_name"] for f in R.resolved_fields(db, "opportunities")}
    check(
        "Administration -> Opportunities -> Fields contains One-Time Revenue",
        "one_time_revenue" in names,
    )
    check(
        "...and licence_model, filed on the Leads sheet by the register",
        "licence_model" in names,
        sorted(n for n in names if "licence" in n),
    )


# =====================================================================
def case_3_one_time_revenue(db) -> None:
    head("3  one_time_revenue — one definition, two placements (D1)")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "one_time_revenue",
        )
    )
    check("canonical definition exists", definition is not None)
    if definition is None:
        return

    placements = {p.module_key: p for p in definition.placements}
    check(
        "placed on exactly Opportunities and Deals",
        set(placements) == {"opportunities", "deals"},
        str(sorted(placements)),
    )
    check(
        "Opportunity owns its value",
        placements["opportunities"].value_mode == "own",
        placements["opportunities"].value_mode,
    )
    check(
        "Deal carries it forward, unlocked (D1)",
        placements["deals"].value_mode == "carry_forward"
        and placements["deals"].value_locked is False
        and placements["deals"].editable is True,
        f"{placements['deals'].value_mode} locked={placements['deals'].value_locked}",
    )
    check(
        "the two placements sit in different sections",
        placements["opportunities"].section.label != placements["deals"].section.label,
        f"{placements['opportunities'].section.label} / {placements['deals'].section.label}",
    )
    check(
        "and are captured at different stages (4 vs 7)",
        placements["opportunities"].capture_stage == 4
        and placements["deals"].capture_stage == 7,
    )

    # Rename propagation: one label, both modules. Done in memory and rolled
    # back — this test proves the model, it does not edit the register.
    original = definition.label
    definition.label = "Annual Revenue"
    db.flush()
    labels = {
        row["module"]: row["label"]
        for row in R.resolved_fields(db)
        if row["api_name"] == "one_time_revenue"
    }
    check(
        "renaming the definition renames it on BOTH modules",
        labels == {"opportunities": "Annual Revenue", "deals": "Annual Revenue"},
        str(labels),
    )
    definition.label = original
    db.rollback()


# =====================================================================
def case_4_project_stage(db) -> None:
    head("4  project_stage — relabelled, and absent from Deals")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "project_stage",
        )
    )
    modules = R.modules_of(db, definition.id)
    check(
        "placed on Leads and Opportunities only",
        modules == ["leads", "opportunities"],
        str(modules),
    )
    check(
        "Deals has no project_stage placement — it has deal_stage",
        "project_stage" not in {f["api_name"] for f in R.resolved_fields(db, "deals")}
        and "deal_stage" in {f["api_name"] for f in R.resolved_fields(db, "deals")},
    )
    labels = {
        row["module"]: row["label"]
        for row in R.resolved_fields(db)
        if row["api_name"] == "project_stage"
    }
    check(
        "the Opportunity placement overrides the label",
        labels.get("opportunities") == "Opportunity Stage"
        and labels.get("leads") == "Lead Stage",
        str(labels),
    )
    check(
        "both own their own value — a Lead's stage is not an Opportunity's",
        all(
            p.value_mode == "own"
            for p in definition.placements
            if p.status == "active"
        ),
    )


# =====================================================================
def case_5_probability_pct(db) -> None:
    head("5  probability_pct — three independent owned values")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "probability_pct",
        )
    )
    modules = R.modules_of(db, definition.id)
    check("one definition, three placements", modules == ["deals", "leads", "opportunities"], str(modules))
    check(
        "every placement owns its own value",
        {p.value_mode for p in definition.placements} == {"own"},
    )
    check(
        "none of them is read-through or carried",
        all(p.storage is not None and p.editable for p in definition.placements),
    )


# =====================================================================
def case_6_progression_pct(db) -> None:
    head("6  progression_pct — D4, a plain editable Number")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "progression_pct",
        )
    )
    check("type is number, not computed", definition.field_type == "number", definition.field_type)
    check("no computed formula", definition.computed_formula is None, str(definition.computed_formula))
    check("no picklist", definition.picklist_key is None)
    check(
        "no placement is marked Computed",
        all(p.requirement != "Computed" for p in definition.placements),
        str({p.module_key: p.requirement for p in definition.placements}),
    )
    check(
        "editable on all three modules",
        all(p.editable for p in definition.placements)
        and len(definition.placements) == 3,
    )


# =====================================================================
def case_7_lead_status(db) -> None:
    head("7  lead_status — placement label overrides")

    labels = {
        row["module"]: row["label"]
        for row in R.resolved_fields(db)
        if row["api_name"] == "lead_status"
    }
    check(
        "each module names it correctly",
        labels
        == {
            "leads": "Lead Status",
            "opportunities": "Opportunity Status",
            "deals": "Deal Status",
        },
        str(labels),
    )
    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "lead_status",
        )
    )
    check(
        "the api_name stays lead_status on all three",
        {p.api_name for p in definition.placements} == {"lead_status"},
    )
    check("one picklist behind all three", definition.picklist_key is not None)


# =====================================================================
def case_8_end_client(db) -> None:
    head("8  end_client — D3, and scope keeps other modules apart")

    pipeline = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "end_client",
        )
    )
    placements = {p.module_key: p for p in pipeline.placements if p.status == "active"}

    check(
        "Deal owns its own value, carried from the parent (D3)",
        placements["deals"].value_mode == "carry_forward"
        and placements["deals"].editable is True
        and placements["deals"].storage == "column",
        placements["deals"].value_mode,
    )
    check(
        "Deal is NOT read-through",
        placements["deals"].value_mode != "read_through",
    )
    check(
        "Opportunity still reads it through the parent",
        placements["opportunities"].value_mode == "read_through"
        and placements["opportunities"].storage is None,
        placements["opportunities"].value_mode,
    )
    check("Lead owns it", placements["leads"].value_mode == "own")

    check(
        "the Deal's value carries from LEADS, past the read-through Opportunity",
        R.value_source(db, "deals", "end_client") == "leads",
        str(R.value_source(db, "deals", "end_client")),
    )

    others = db.scalars(
        select(FieldDefinition).where(
            FieldDefinition.api_name == "end_client",
            FieldDefinition.scope_key != "pipeline",
        )
    ).all()
    check(
        "Partners and Quotes keep their own separate definitions",
        {d.scope_key for d in others} == {"partners", "quotes"},
        str(sorted(d.scope_key for d in others)),
    )

    cp = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "customer_partner_si",
        )
    )
    deal_cp = next(p for p in cp.placements if p.module_key == "deals")
    check(
        "customer_partner_si follows the same rule on Deals",
        deal_cp.value_mode == "carry_forward" and deal_cp.editable,
        deal_cp.value_mode,
    )


# =====================================================================
def case_9_read_through(db) -> None:
    head("9  read-through — stores nothing, resolves to the parent")

    plan = R.read_through_plan(db, "opportunities")
    # 27 since Pursuit Groups: fx_rate_at_entry reads through beside currency.
    check("Opportunities reads 27 fields through", len(plan) == 27, str(len(plan)))
    check("every one of them resolves to leads", set(plan.values()) == {"leads"})

    rows = [
        f for f in R.resolved_fields(db, "opportunities") if f["value_mode"] == "read_through"
    ]
    check(
        "none is editable and none declares storage",
        all(f["editable"] is False for f in rows)
        and all(
            p.storage is None
            for p in R.placements_of(db, "opportunities", value_mode="read_through").values()
        ),
    )
    check(
        "each names the module and the link it resolves through",
        all(f["read_through_from"] == "leads" for f in rows)
        and all(f["read_through_via"] == "parent_lead" for f in rows),
    )
    check(
        "segment is read through rather than stored on the Opportunity",
        "segment" in plan,
        str(sorted(plan)[:6]),
    )


# =====================================================================
def case_10_shared(db) -> None:
    head("10  shared field — one definition, explicit modes")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "stage_skip_reason",
        )
    )
    modules = R.modules_of(db, definition.id)
    check(
        "one definition across all three pipeline modules",
        modules == ["deals", "leads", "opportunities"],
        str(modules),
    )
    check(
        "each placement states its own value behaviour explicitly",
        {p.value_mode for p in definition.placements} == {"own"},
    )
    check(
        "'shared' is not a value mode — it is the placement count",
        len(modules) > 1
        and not db.execute(
            text("SELECT count(*) FROM field_placements WHERE value_mode = 'shared'")
        ).scalar(),
    )


# =====================================================================
def case_11_admin_created(db) -> None:
    head("11  Administration-created field, deleted in the register")

    definition = db.scalar(
        select(FieldDefinition).where(FieldDefinition.api_name == "rfp_document_file")
    )
    check("one definition", definition is not None)
    active = [p for p in definition.placements if p.status == "active"]
    deleted = [p for p in definition.placements if p.status == "deleted"]

    # RFP Document File was deleted in Administration on 15 Sep 2026 (register
    # version 109) and confirmed deliberate on 16 Sep. The case is kept rather
    # than removed, because what it now proves is the thing that matters about
    # an Administration field: deleting one is LOGICAL. No DDL ran, the
    # definition is still here, the placement is still here marked deleted, and
    # every value ever stored under this api_name is untouched in the JSONB —
    # which is what makes Administration's restore real rather than a promise.
    check("no active placement — it renders nowhere", not active, str(len(active)))
    check("exactly one deleted placement", len(deleted) == 1, str(len(deleted)))
    check(
        "it was placed on Opportunities — a Stage 4 field",
        deleted[0].module_key == "opportunities",
        deleted[0].module_key,
    )
    check(
        "its values live in custom_fields, never a column",
        deleted[0].storage == "custom_fields",
        str(deleted[0].storage),
    )
    check(
        "the custom-field writer no longer accepts it on Opportunities",
        "rfp_document_file" not in custom_field_defs(db, "opportunities"),
    )
    check(
        "and it never reached Leads",
        "rfp_document_file" not in custom_field_defs(db, "leads", include_deleted=True),
    )
    check(
        "the deleted placement is still there to restore from",
        "rfp_document_file" in custom_field_defs(db, "opportunities", include_deleted=True),
    )
    # demo_field has been deleted in Administration too, so the scoping is read
    # through the deleted placements. The rule under test is unchanged and is
    # the one that matters: a placement belongs to ONE module, and deleting it
    # does not smear it across the others.
    check(
        "demo_field, a Stage 0 field, is scoped to Leads alone",
        "demo_field" in custom_field_defs(db, "leads", include_deleted=True)
        and "demo_field" not in custom_field_defs(db, "opportunities", include_deleted=True),
    )


# =====================================================================
CARRIED = (
    "one_time_revenue",
    "arr_annual_recurring",
    "3rd_party_one_time",
    "3rd_party_recurring_per_year",
    "contract_years",
)


def case_12_carry_forward_live(db) -> None:
    head("12  CARRY-FORWARD, live — real records (D1, D3, D5)")

    lead_id, opp_id, deal_id = "LEAD-T9001", "OPP-T9001", "DEAL-T9001"
    account = db.execute(text("SELECT account_id FROM accounts LIMIT 1")).scalar()

    _cleanup(db)

    lead = Lead(
        lead_id=lead_id,
        opportunity_name="Carry-forward probe",
        is_primary_pursuit=True,
        lighthouse_project=False,
        gorilla_flag=False,
        demo_agreed=False,
        demo_completed=False,
        project_team_access_confirmed=False,
        budget_confirmed=False,
        active=True,
        end_client=account,
        customer_partner_si=account,
    )
    db.add(lead)

    opportunity = Opportunity(
        opportunity_id=opp_id,
        parent_lead=lead_id,
        nomination_bid=False,
        incumbent_only=False,
        pay_when_paid=False,
        is_low_hanging=False,
        is_top_10=False,
        active=True,
        one_time_revenue=1000,
        arr_annual_recurring=2000,
        contract_years=5,
        # X6.1 is enforced when a Deal is created from an Opportunity (app/
        # revenue.py, 13 Sep 2026): the negotiated value must equal TCV =
        # 2000 × 5 + 1000 + 300 + 400 × 5.
        final_negotiated_value=13300,
    )
    opportunity.third_party_one_time = 300
    opportunity.third_party_recurring_per_year = 400
    db.add(opportunity)
    db.commit()

    # The Deal is created through the ACTUAL API, so the router path that
    # section 10 of the brief requires is what gets exercised.
    response = client.post(
        "/api/deals",
        json={
            "deal_id": deal_id,
            "deal_name": "Carry-forward probe",
            "parent_opportunity": opp_id,
        },
    )
    check(f"POST /api/deals created the record", response.status_code == 201, response.text[:300])
    if response.status_code != 201:
        _cleanup(db)
        return

    deal = db.get(Deal, deal_id)
    db.refresh(deal)

    check(
        "money fields carried forward from the Opportunity",
        deal.one_time_revenue == 1000
        and deal.arr_annual_recurring == 2000
        and deal.third_party_one_time == 300
        and deal.third_party_recurring_per_year == 400
        and deal.contract_years == 5,
        f"otr={deal.one_time_revenue} arr={deal.arr_annual_recurring} "
        f"3po={deal.third_party_one_time} yrs={deal.contract_years}",
    )
    check(
        "end_client carried from the LEAD, past the read-through Opportunity (D3)",
        deal.end_client == account,
        f"{deal.end_client!r} vs {account!r}",
    )
    check(
        "customer_partner_si the same",
        deal.customer_partner_si == account,
        str(deal.customer_partner_si),
    )
    check(
        "the Opportunity has no end_client column to have copied from",
        not hasattr(Opportunity, "end_client")
        or getattr(opportunity, "end_client", None) is None,
    )

    # ---- afterwards the Deal OWNS it and may diverge (D1: value_locked false)
    patched = client.patch(f"/api/deals/{deal_id}", json={"one_time_revenue": 850})
    check("the Deal may renegotiate a carried value", patched.status_code == 200, patched.text[:200])
    db.expire_all()
    deal = db.get(Deal, deal_id)
    check("the Deal's value diverged to 850", deal.one_time_revenue == 850, str(deal.one_time_revenue))

    opportunity = db.get(Opportunity, opp_id)
    check(
        "and the Opportunity is UNCHANGED at 1000 — it was a copy, not a link",
        opportunity.one_time_revenue == 1000,
        str(opportunity.one_time_revenue),
    )

    # ---- an explicitly supplied value is never overwritten by inheritance
    # No cleanup here: the run-start _cleanup already cleared any leftovers,
    # and clearing again would take OPP-T9001 with it.
    #
    # Its own Opportunity, a copy of the first. OPP-T9001 became DEAL-T9001
    # above, and an Opportunity converts once (app/conversion.py) — a second
    # Deal from it is refused, which is the point of that rule, not of this test.
    from sqlalchemy import inspect as sa_inspect

    db.expire_all()
    source = db.get(Opportunity, opp_id)
    opp2 = "OPP-T9002"
    copy = {a.key: getattr(source, a.key) for a in sa_inspect(Opportunity).column_attrs if a.key != "opportunity_id"}
    db.add(Opportunity(opportunity_id=opp2, **{**copy, "lead_status": "OPEN"}))
    db.commit()

    deal2 = "DEAL-T9002"
    response = client.post(
        "/api/deals",
        json={
            "deal_id": deal2,
            "deal_name": "Explicit wins",
            "parent_opportunity": opp2,
            "one_time_revenue": 7,
        },
    )
    if response.status_code == 201:
        db.expire_all()
        check(
            "an explicitly sent value beats the inherited one",
            db.get(Deal, deal2).one_time_revenue == 7,
            str(db.get(Deal, deal2).one_time_revenue),
        )
        check(
            "while the unsent ones still carry",
            db.get(Deal, deal2).arr_annual_recurring == 2000,
        )
    else:
        check("second deal created", False, response.text[:200])

    # ---- a Deal with no parent inherits nothing, and does not crash
    deal3 = "DEAL-T9003"
    response = client.post(
        "/api/deals", json={"deal_id": deal3, "deal_name": "Orphan"}
    )
    if response.status_code == 201:
        db.expire_all()
        check(
            "a Deal with no parent link carries nothing and does not fail",
            db.get(Deal, deal3).one_time_revenue is None,
            str(db.get(Deal, deal3).one_time_revenue),
        )
    else:
        check("parentless deal created", False, response.text[:200])

    _cleanup(db)


def _cleanup(db, *_ignored) -> None:
    """
    Remove every probe record, child rows first.

    Deletes by PREFIX rather than by id, and in dependency order, so a run that
    failed half way through does not leave rows that break the NEXT run's
    setup. A Deal references its Opportunity, which references its Lead, so
    anything else violates deals_parent_opportunity_fkey.
    """
    for table, column in (
        ("deals", "deal_id"),
        ("opportunities", "opportunity_id"),
        ("leads", "lead_id"),
    ):
        db.execute(text(f"DELETE FROM {table} WHERE {column} LIKE 'DEAL-T9%%' "
                        f"OR {column} LIKE 'OPP-T9%%' OR {column} LIKE 'LEAD-T9%%'"))
    db.commit()


# =====================================================================
def case_13_delete_restore(db) -> None:
    head("13  delete and restore — placement vs definition")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "one_time_revenue",
        )
    )
    before = R.modules_of(db, definition.id)

    # --- remove from ONE module
    response = client.delete(
        f"/api/admin/metadata/placements/{_placement_id(db, definition.id, 'deals')}"
    )
    check("DELETE placement returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the field disappears from Deals only",
        R.modules_of(db, definition.id) == ["opportunities"],
        str(R.modules_of(db, definition.id)),
    )
    check(
        "the canonical definition is untouched",
        db.get(FieldDefinition, definition.id).status == "active",
    )
    check(
        "the business column and its values survive",
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='deals' AND column_name='one_time_revenue'"
            )
        ).scalar()
        == 1,
    )
    placement = db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.definition_id == definition.id,
            FieldPlacement.module_key == "deals",
        )
    )
    check(
        "the placement is logically deleted, not cascaded",
        placement.status == "deleted" and placement.deleted_by_cascade is False,
        f"{placement.status} cascade={placement.deleted_by_cascade}",
    )

    # --- restore it
    response = client.post(
        f"/api/admin/metadata/placements/{placement.id}/restore"
    )
    check("POST placement restore returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the field comes back on Deals, in its own section",
        R.modules_of(db, definition.id) == before,
        str(R.modules_of(db, definition.id)),
    )

    # --- delete the whole definition, then restore
    response = client.delete(f"/api/admin/metadata/fields/{definition.id}")
    check("DELETE definition returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the definition is deleted",
        db.get(FieldDefinition, definition.id).status == "deleted",
    )
    cascaded = db.scalars(
        select(FieldPlacement).where(FieldPlacement.definition_id == definition.id)
    ).all()
    check(
        "every placement went with it, flagged as a cascade",
        all(p.status == "deleted" and p.deleted_by_cascade for p in cascaded),
        str([(p.module_key, p.status, p.deleted_by_cascade) for p in cascaded]),
    )
    check(
        "it renders nowhere",
        "one_time_revenue"
        not in {f["api_name"] for f in R.resolved_fields(db, "deals")},
    )

    response = client.post(f"/api/admin/metadata/fields/{definition.id}/restore")
    check("POST definition restore returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the definition and both placements come back",
        db.get(FieldDefinition, definition.id).status == "active"
        and R.modules_of(db, definition.id) == before,
        str(R.modules_of(db, definition.id)),
    )
    check(
        "no dynamic DDL was issued — the column was never touched",
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='deals' AND column_name='one_time_revenue'"
            )
        ).scalar()
        == 1,
    )


def _placement_id(db, definition_id: int, module: str) -> int:
    return db.scalar(
        select(FieldPlacement.id).where(
            FieldPlacement.definition_id == definition_id,
            FieldPlacement.module_key == module,
            FieldPlacement.status == "active",
        )
    )


# =====================================================================
def case_14_integrity(db) -> None:
    head("14  database integrity — the constraints refuse what they must")

    definition = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "one_time_revenue",
        )
    )

    def refuses(name: str, make) -> None:
        try:
            make()
            db.flush()
            check(name, False, "the database ACCEPTED it")
        except IntegrityError:
            check(name, True)
        finally:
            db.rollback()

    refuses(
        "a second definition of one_time_revenue in the pipeline scope",
        lambda: db.add(
            FieldDefinition(
                scope_key="pipeline",
                api_name="one_time_revenue",
                label="Duplicate",
                field_type="currency",
                origin="test",
            )
        ),
    )

    existing = db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.definition_id == definition.id,
            FieldPlacement.module_key == "deals",
        )
    )
    refuses(
        "a second placement of one definition on one module",
        lambda: db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name="one_time_revenue",
                module_key="deals",
                scope_key="deals",
                section_id=existing.section_id,
                requirement="Optional",
                storage="column",
            )
        ),
    )

    other = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == "pipeline",
            FieldDefinition.api_name == "contract_years",
        )
    )
    refuses(
        "two different definitions colliding on one module under one api_name",
        lambda: db.add(
            FieldPlacement(
                definition_id=other.id,
                api_name="contract_years",
                module_key="deals",
                scope_key="deals",
                section_id=existing.section_id,
                requirement="Optional",
                storage="column",
            )
        ),
    )

    refuses(
        "a read-through placement that also claims storage",
        lambda: db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name="one_time_revenue",
                module_key="leads",
                scope_key="leads",
                section_id=existing.section_id,
                requirement="Optional",
                value_mode="read_through",
                editable=False,
                storage="column",
            )
        ),
    )

    refuses(
        "an invalid value_mode",
        lambda: db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name="one_time_revenue",
                module_key="leads",
                scope_key="leads",
                section_id=existing.section_id,
                requirement="Optional",
                value_mode="own_instance",
                storage="column",
            )
        ),
    )

    refuses(
        "value_locked on a field that carries nothing",
        lambda: db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name="one_time_revenue",
                module_key="leads",
                scope_key="leads",
                section_id=existing.section_id,
                requirement="Optional",
                value_mode="own",
                value_locked=True,
                storage="column",
            )
        ),
    )

    refuses(
        "a placement whose api_name disagrees with its definition",
        lambda: db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name="not_the_same_name",
                module_key="leads",
                scope_key="leads",
                section_id=existing.section_id,
                requirement="Optional",
                storage="column",
            )
        ),
    )


# =====================================================================
def case_15_architecture(db) -> None:
    head("15  architecture — one resolver, no dynamic DDL")

    app_dir = Path(__file__).resolve().parent / "app"
    sources = {p: p.read_text(encoding="utf-8") for p in app_dir.rglob("*.py")}

    # Comments and docstrings explain the architecture and necessarily NAME the
    # things it forbids. Only executable code is searched, or every file that
    # documents the rule would be reported as breaking it.
    code = {p: _strip_comments(text_) for p, text_ in sources.items()}

    importers = sorted(
        p.name
        for p, text_ in code.items()
        if re.search(r"^\s*(from|import)\s+rebuild_metadata\b", text_, re.M)
        or re.search(r"\bimport_module\(\s*[\"']rebuild_metadata", text_)
    )
    check(
        "no module under app/ imports the one-shot migration port",
        not importers,
        str(importers),
    )

    ddl = sorted(
        p.name
        for p, text_ in code.items()
        if re.search(r"\b(ALTER\s+TABLE|DROP\s+COLUMN|DROP\s+TABLE|CREATE\s+TABLE)\b",
                     text_, re.I)
    )
    check("no dynamic DDL in app/ code", not ddl, str(ddl))

    check(
        "field_metadata is no longer read by the metadata layer",
        all(
            "FieldMetadata" not in code[app_dir / name]
            for name in ("metadata_spec.py", "metadata_resolver.py", "custom_fields.py")
        ),
    )
    check(
        "the Administration API no longer queries field_metadata",
        "FieldMetadata" not in code[app_dir / "routers" / "metadata.py"],
    )
    check(
        "source_modules_for is gone",
        "def source_modules_for" not in sources[app_dir / "module_split.py"],
    )

    # the archive is still there and still complete
    archived = db.execute(
        text("SELECT count(*) FROM field_metadata_pre_round7")
    ).scalar()
    live = db.execute(text("SELECT count(*) FROM field_metadata")).scalar()
    check(
        f"the pre-Round-7 archive is intact ({archived} rows)",
        archived == live == 568,
        f"archive={archived} field_metadata={live}",
    )


def _strip_comments(source: str) -> str:
    """Executable code only — docstrings and # comments removed."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = []
    for line in source.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split("  #")[0])
    text_ = "\n".join(out)
    for doc in docstrings:
        text_ = text_.replace(doc, "")
    return text_


# =====================================================================
def main() -> int:
    db = SessionLocal()
    try:
        print("=" * 74)
        print("ROUND 7 — FIELD PLACEMENT MODEL")
        print("=" * 74)
        for case in (
            case_1_no_duplicates,
            case_2_administration_sees_the_crm,
            case_3_one_time_revenue,
            case_4_project_stage,
            case_5_probability_pct,
            case_6_progression_pct,
            case_7_lead_status,
            case_8_end_client,
            case_9_read_through,
            case_10_shared,
            case_11_admin_created,
            case_12_carry_forward_live,
            case_13_delete_restore,
            case_14_integrity,
            case_15_architecture,
        ):
            try:
                case(db)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                check(f"{case.__name__} raised", False, f"{type(exc).__name__}: {exc}")
        print("\n" + "=" * 74)
        if FAILED:
            print(f"{PASSED} passed, {len(FAILED)} FAILED\n")
            for line in FAILED:
                print("   ", line)
            return 1
        print(f"ALL {PASSED} CHECKS PASSED")
        print("=" * 74)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

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
    3   one_time_revenue        two fields, copied once by Conversion Mapping
    4   project_stage           a field of Leads and one of Opportunities
    5   probability_pct         three fields, three owned values
    6   progression_pct         D4 — plain editable Number
    7   lead_status             three fields, three status lists (G3)
    8   end_client              the Lead's, shown live on Opportunity and Deal (G1)
    9   read-through            stores nothing, not editable, resolves to parent
    10  one field per module    stage_skip_reason is three independent fields
    11  admin-created field     one definition, one placement, custom_fields
    12  CARRY-FORWARD, LIVE     real records: seeded, then diverging
    13  delete / restore        placement vs definition, and the cascade flag
    14  database integrity      the constraints refuse what they must
    15  architecture            no second projection, no dynamic DDL
    16  Administration rules    owned once, local lists, system values, modules offered

Metadata v2 (24 Sep 2026): every field is owned by exactly one module.
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

# Every route is mounted behind require_access / require_administration, which read a
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
def owned(db, module: str, api_name: str) -> FieldDefinition | None:
    """The definition a module OWNS under this name (metadata v2)."""
    return db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == module,
            FieldDefinition.api_name == api_name,
        )
    )


def case_1_no_duplicates(db) -> None:
    head("1  one module owns each field — no duplicates, no shared scope")

    rows = db.execute(
        text(
            "SELECT scope_key, api_name, count(*) FROM field_definitions "
            "GROUP BY scope_key, api_name HAVING count(*) > 1"
        )
    ).all()
    check("no two definitions share (scope_key, api_name)", not rows, str(rows))

    shared = db.execute(
        text("SELECT count(*) FROM field_definitions WHERE scope_key = 'pipeline'")
    ).scalar()
    check("the shared pipeline scope is gone (metadata v2)", shared == 0, f"got {shared}")

    # Zoho's rule: Opportunities and Deals each OWN a One-Time Revenue.
    scopes = sorted(
        db.scalars(
            select(FieldDefinition.scope_key).where(FieldDefinition.api_name == "one_time_revenue")
        )
    )
    check(
        "one_time_revenue is a field of Opportunities and a field of Deals",
        scopes == ["deals", "opportunities", "quotes"] or scopes == ["deals", "opportunities"],
        str(scopes),
    )

    owners = db.execute(
        text(
            "SELECT definition_id, count(*) FROM field_placements "
            "WHERE value_mode <> 'read_through' GROUP BY 1 HAVING count(*) > 1"
        )
    ).all()
    check("every field has exactly one owning module", not owners, str(owners[:5]))

    wrong_owner = db.execute(
        text(
            "SELECT d.api_name, d.scope_key, p.module_key FROM field_placements p "
            "JOIN field_definitions d ON d.id = p.definition_id "
            "WHERE p.value_mode <> 'read_through' AND d.scope_key <> p.module_key "
            "AND d.scope_key NOT LIKE p.module_key || '\\_\\_%'"
        )
    ).all()
    check("a field's owning placement is on the module that owns it", not wrong_owner, str(wrong_owner[:5]))

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

    # Counts unchanged by metadata v2 (24 Sep 2026): the Deal's End Client
    # moved from Commercial Terms to From the Lead, which is one field either
    # way. History of these numbers is in git.
    for module, expected in (("leads", 81), ("opportunities", 107), ("deals", 98)):
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
    head("3  one_time_revenue — two fields, copied once at conversion")

    opportunity = owned(db, "opportunities", "one_time_revenue")
    deal = owned(db, "deals", "one_time_revenue")
    check("Opportunities and Deals each own one", opportunity is not None and deal is not None)
    if opportunity is None or deal is None:
        return
    check("the Opportunity's is only on Opportunities", R.modules_of(db, opportunity.id) == ["opportunities"])
    check("the Deal's is only on Deals", R.modules_of(db, deal.id) == ["deals"])

    deal_placement = next(p for p in deal.placements if p.module_key == "deals")
    opp_placement = next(p for p in opportunity.placements if p.module_key == "opportunities")
    check("the Opportunity owns its value", opp_placement.value_mode == "own")
    # Locked since 16 Sep 2026 — no commercial value changes after Commercial
    # Evaluation. Case 12 proves the lock is enforced by value.
    check(
        "the Deal's arrives at conversion and is LOCKED",
        deal_placement.value_mode == "carry_forward" and deal_placement.value_locked is True,
        f"{deal_placement.value_mode} locked={deal_placement.value_locked}",
    )
    check(
        "Conversion Mapping says where it comes from",
        R.carry_forward_plan(db, "deals").get("one_time_revenue") == ("opportunities", "one_time_revenue"),
        str(R.carry_forward_plan(db, "deals").get("one_time_revenue")),
    )
    check(
        "and are captured at different stages (4 vs 7)",
        opp_placement.capture_stage == 4 and deal_placement.capture_stage == 7,
    )

    # Zoho's rule, the reason for v2: renaming one module's field leaves the
    # other alone. Done in memory and rolled back.
    original = deal.label
    deal.label = "Annual Revenue"
    db.flush()
    labels = {
        row["module"]: row["label"]
        for row in R.resolved_fields(db)
        if row["api_name"] == "one_time_revenue" and row["module"] in ("opportunities", "deals")
    }
    check(
        "renaming it on Deals leaves Opportunities alone",
        labels == {"opportunities": opportunity.label, "deals": "Annual Revenue"},
        str(labels),
    )
    deal.label = original
    db.rollback()


# =====================================================================
def case_4_project_stage(db) -> None:
    head("4  project_stage — a field of Leads and a field of Opportunities")

    lead = owned(db, "leads", "project_stage")
    opportunity = owned(db, "opportunities", "project_stage")
    check("each owns one", lead is not None and opportunity is not None)
    if lead is None or opportunity is None:
        return
    check(
        "Deals has no project_stage — it has deal_stage",
        "project_stage" not in {f["api_name"] for f in R.resolved_fields(db, "deals")}
        and "deal_stage" in {f["api_name"] for f in R.resolved_fields(db, "deals")},
    )
    check(
        "each is named in its own label, with no override",
        lead.label == "Lead Stage"
        and opportunity.label == "Opportunity Stage"
        and all(p.label_override is None for p in (*lead.placements, *opportunity.placements)),
        f"{lead.label} / {opportunity.label}",
    )
    check(
        "both use the one global stage list",
        lead.picklist_key == opportunity.picklist_key
        and db.execute(
            text("SELECT is_global FROM picklists WHERE picklist_key = :k"), {"k": lead.picklist_key}
        ).scalar() is True,
    )


# =====================================================================
def case_5_probability_pct(db) -> None:
    head("5  probability_pct — three fields, three owned values")

    fields = {m: owned(db, m, "probability_pct") for m in ("leads", "opportunities", "deals")}
    check("each pipeline module owns one", all(fields.values()), str({m: bool(d) for m, d in fields.items()}))
    placements = [p for d in fields.values() if d for p in d.placements]
    check("every one owns its own value", {p.value_mode for p in placements} == {"own"})
    check("none is read-through or carried", all(p.storage is not None and p.editable for p in placements))


# =====================================================================
def case_6_progression_pct(db) -> None:
    head("6  progression_pct — D4, a plain editable Number")

    for module in ("leads", "opportunities", "deals"):
        definition = owned(db, module, "progression_pct")
        if definition is None:
            check(f"{module} owns progression_pct", False)
            continue
        check(
            f"{module}: a number, no formula, no picklist",
            definition.field_type == "number"
            and definition.computed_formula is None
            and definition.picklist_key is None,
            definition.field_type,
        )
        check(
            f"{module}: editable and not Computed",
            all(p.editable and p.requirement != "Computed" for p in definition.placements),
        )


# =====================================================================
def case_7_lead_status(db) -> None:
    head("7  lead_status — three fields, three status lists (G3)")

    labels = {
        row["module"]: row["label"]
        for row in R.resolved_fields(db)
        if row["api_name"] == "lead_status"
    }
    check(
        "each module names it correctly",
        labels == {"leads": "Lead Status", "opportunities": "Opportunity Status", "deals": "Deal Status"},
        str(labels),
    )
    lists = {m: owned(db, m, "lead_status").picklist_key for m in ("leads", "opportunities", "deals")}
    check(
        "each module has its own list",
        lists == {
            "leads": "leads__lead_status",
            "opportunities": "opportunities__lead_status",
            "deals": "deals__lead_status",
        },
        str(lists),
    )

    def active_keys(key: str) -> set[str]:
        return set(
            db.scalars(
                text("SELECT key FROM picklist_values WHERE picklist_key = :k AND active").bindparams(k=key)
            )
        )

    check(
        "POC/Pilot Deal is offered on Deals only",
        "POC_PILOT_DEAL" in active_keys(lists["deals"])
        and "POC_PILOT_DEAL" not in active_keys(lists["leads"])
        and "POC_PILOT_DEAL" not in active_keys(lists["opportunities"]),
    )
    system = set(
        db.scalars(
            text("SELECT key FROM picklist_values WHERE picklist_key = 'deals__lead_status' AND is_system")
        )
    )
    check(
        "the values the server reads by key are protected",
        system == {"OPEN", "ON_HOLD", "CLOSED_LOST", "CONVERTED", "POC_PILOT_DEAL"},
        str(sorted(system)),
    )


# =====================================================================
def case_8_end_client(db) -> None:
    head("8  end_client — the Lead's, shown live on the Opportunity and the Deal (G1)")

    lead = owned(db, "leads", "end_client")
    check("Leads owns End Client", lead is not None)
    if lead is None:
        return
    placements = {p.module_key: p for p in lead.placements if p.status == "active"}
    for module in ("opportunities", "deals"):
        p = placements.get(module)
        check(
            f"{module} shows the Lead's, live — stores nothing, not editable",
            p is not None and p.value_mode == "read_through" and p.storage is None and p.editable is False,
            p.value_mode if p else "missing",
        )
    check(
        "the Deal's resolves to LEADS",
        R.value_source(db, "deals", "end_client") == "leads",
        str(R.value_source(db, "deals", "end_client")),
    )
    check(
        "Deals owns no End Client of its own",
        owned(db, "deals", "end_client") is None,
    )
    others = sorted(
        db.scalars(
            select(FieldDefinition.scope_key).where(
                FieldDefinition.api_name == "end_client",
                FieldDefinition.scope_key != "leads",
            )
        )
    )
    check(
        "Deal Registrations and Quotes keep their own separate End Client",
        others == ["quotes", "registrations"],
        str(others),
    )

    customer = owned(db, "deals", "customer_partner_si")
    deal_cp = next((p for p in customer.placements if p.module_key == "deals"), None) if customer else None
    check(
        "Customer (Partner / SI) is the Deal's own, copied at conversion and locked",
        deal_cp is not None and deal_cp.value_mode == "carry_forward" and deal_cp.value_locked,
    )
    check(
        "…from the Lead, past the Opportunity that shows it",
        R.carry_forward_plan(db, "deals").get("customer_partner_si") == ("leads", "customer_partner_si"),
        str(R.carry_forward_plan(db, "deals").get("customer_partner_si")),
    )


# =====================================================================
def case_9_read_through(db) -> None:
    head("9  read-through — stores nothing, resolves to the parent")

    plan = R.read_through_plan(db, "opportunities")
    # 27 since Pursuit Groups: fx_rate_at_entry reads through beside currency.
    check("Opportunities reads 27 fields through", len(plan) == 27, str(len(plan)))
    check("every one of them resolves to leads", set(plan.values()) == {"leads"})
    deals = R.read_through_plan(db, "deals")
    # 25 before G1; End Client joined them on 24 Sep 2026.
    check("Deals reads 26 through (End Client since G1)", len(deals) == 26, str(len(deals)))

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
        "they sit in the From the Lead section",
        {f["section"] for f in rows} == {"From the Lead"},
        str({f["section"] for f in rows}),
    )


# =====================================================================
def case_10_shared(db) -> None:
    head("10  a field every module has — one each, independent")

    fields = {m: owned(db, m, "stage_skip_reason") for m in ("leads", "opportunities", "deals")}
    check("each pipeline module owns its own", all(fields.values()))
    if not all(fields.values()):
        return
    check(
        "three different fields, not one field shown three times",
        len({d.id for d in fields.values()}) == 3,
    )
    check(
        "'shared' is not a value mode",
        not db.execute(
            text("SELECT count(*) FROM field_placements WHERE value_mode = 'shared'")
        ).scalar(),
    )


# =====================================================================
def case_11_admin_created(db) -> None:
    head("11  Administration-deleted fields, purged at go-live")

    # RFP Document File (an Administration field on Opportunities) and Demo
    # Field (Leads) were deleted in Administration in September 2026, and this
    # case proved a delete was LOGICAL — the rows kept, marked deleted, ready to
    # restore. Version 1 went live with no prototype history
    # (fresh_start_register.py, 21 Sep 2026), which removed deleted fields for
    # good. Logical delete and restore are still tested, on a field those tests
    # create themselves: test_metadata_round6.py and test_round6_gaps.py.
    for name in ("rfp_document_file", "demo_field"):
        check(
            f"{name} is gone from the register",
            db.scalar(select(FieldDefinition).where(FieldDefinition.api_name == name)) is None,
        )
    check(
        "no deleted placement is left over from the prototype",
        not db.execute(text("SELECT count(*) FROM field_placements WHERE status = 'deleted'")).scalar(),
    )
    check(
        "the custom-field writer does not accept it on Opportunities",
        "rfp_document_file" not in custom_field_defs(db, "opportunities", include_deleted=True),
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
    # G1 (24 Sep 2026): the Deal stores no End Client; it shows the Lead's.
    check(
        "the Deal stores no End Client of its own (G1)",
        deal.end_client is None,
        f"{deal.end_client!r}",
    )
    check(
        "…and shows the Lead's, past the read-through Opportunity",
        carry_forward.effective_value(db, "deals", deal, "end_client") == account,
        str(carry_forward.effective_value(db, "deals", deal, "end_client")),
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

    # ---- afterwards the value is LOCKED on the Deal (D1 reversed 16 Sep 2026)
    # The form re-sends its whole section on every save, so re-sending the
    # value it already holds must succeed; only a CHANGE is refused. The lock
    # used to refuse on mere presence, which would have failed every save.
    resent = client.patch(f"/api/deals/{deal_id}", json={"one_time_revenue": 1000})
    check("re-sending the locked value unchanged is accepted", resent.status_code == 200, resent.text[:200])

    patched = client.patch(f"/api/deals/{deal_id}", json={"one_time_revenue": 850})
    check(
        "changing a locked carried value is refused (422 VALUE_LOCKED)",
        patched.status_code == 422 and "VALUE_LOCKED" in patched.text,
        f"{patched.status_code} {patched.text[:200]}",
    )
    db.expire_all()
    deal = db.get(Deal, deal_id)
    check("the Deal's value is still 1000", deal.one_time_revenue == 1000, str(deal.one_time_revenue))

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

    definition = owned(db, "deals", "one_time_revenue")
    before = R.modules_of(db, definition.id)
    opportunity_before = {f["api_name"] for f in R.resolved_fields(db, "opportunities")}

    # --- remove its placement
    response = client.delete(
        f"/api/admin/metadata/placements/{_placement_id(db, definition.id, 'deals')}"
    )
    check("DELETE placement returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the field disappears from Deals",
        R.modules_of(db, definition.id) == [],
        str(R.modules_of(db, definition.id)),
    )
    check(
        "…and Opportunities' own One-Time Revenue is untouched",
        "one_time_revenue" in {f["api_name"] for f in R.resolved_fields(db, "opportunities")}
        and {f["api_name"] for f in R.resolved_fields(db, "opportunities")} == opportunity_before,
    )
    check(
        "the definition itself is untouched",
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

    response = client.post(
        f"/api/admin/metadata/placements/{placement.id}/restore"
    )
    check("POST placement restore returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the field comes back on Deals",
        R.modules_of(db, definition.id) == before,
        str(R.modules_of(db, definition.id)),
    )

    # --- delete the whole definition, then restore
    response = client.delete(f"/api/admin/metadata/fields/{definition.id}")
    check("DELETE definition returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check("the definition is deleted", db.get(FieldDefinition, definition.id).status == "deleted")
    cascaded = db.scalars(
        select(FieldPlacement).where(FieldPlacement.definition_id == definition.id)
    ).all()
    check(
        "its placement went with it, flagged as a cascade",
        all(p.status == "deleted" and p.deleted_by_cascade for p in cascaded),
        str([(p.module_key, p.status, p.deleted_by_cascade) for p in cascaded]),
    )
    check(
        "it renders nowhere on Deals",
        "one_time_revenue" not in {f["api_name"] for f in R.resolved_fields(db, "deals")},
    )

    response = client.post(f"/api/admin/metadata/fields/{definition.id}/restore")
    check("POST definition restore returns 200", response.status_code == 200, response.text[:200])
    db.expire_all()
    check(
        "the definition and its placement come back",
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

    definition = owned(db, "deals", "one_time_revenue")
    opportunity_owned = owned(db, "opportunities", "one_time_revenue")

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
        "a second One-Time Revenue owned by Deals",
        lambda: db.add(
            FieldDefinition(
                scope_key="deals",
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
        "a second placement of one field on one module",
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

    other = owned(db, "opportunities", "contract_years")
    refuses(
        "two different fields colliding on one module under one api_name",
        lambda: db.add(
            FieldPlacement(
                definition_id=other.id,
                api_name="contract_years",
                module_key="deals",
                scope_key="deals",
                section_id=existing.section_id,
                requirement="Optional",
                value_mode="read_through",
                editable=False,
            )
        ),
    )

    # THE v2 guarantee, in the database: a field has one owning module.
    refuses(
        "a second module OWNING the Opportunity's One-Time Revenue",
        lambda: db.add(
            FieldPlacement(
                definition_id=opportunity_owned.id,
                api_name="one_time_revenue",
                module_key="leads",
                scope_key="leads",
                section_id=existing.section_id,
                requirement="Optional",
                value_mode="own",
                storage="custom_fields",
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
                value_mode="read_through",
                editable=False,
                value_locked=True,
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
                value_mode="read_through",
                editable=False,
            )
        ),
    )


# =====================================================================
def case_16_administration_rules(db) -> None:
    head("16  Administration keeps the v2 rules — refusals, no writes")

    lead_field = owned(db, "leads", "deal_source")
    section = db.scalar(select(FieldPlacement.section_id).where(FieldPlacement.module_key == "accounts"))
    r = client.post(
        f"/api/admin/metadata/fields/{lead_field.id}/placements",
        json={"module_key": "accounts", "section_id": section, "value_mode": "own"},
    )
    check(
        "a Lead's field cannot be given to Accounts too",
        r.status_code == 422 and r.json().get("detail", {}).get("code") == "FIELD_OWNED_ELSEWHERE",
        r.text[:200],
    )
    deal_section = db.scalar(select(FieldPlacement.section_id).where(FieldPlacement.module_key == "deals"))
    r = client.post(
        f"/api/admin/metadata/fields/{lead_field.id}/placements",
        json={"module_key": "deals", "section_id": deal_section, "value_mode": "own"},
    )
    check(
        "…nor owned by Deals — only shown there, from the Lead",
        r.status_code == 422 and r.json().get("detail", {}).get("code") == "FIELD_OWNED_ELSEWHERE",
        r.text[:200],
    )

    lead_section = db.scalar(select(FieldPlacement.section_id).where(FieldPlacement.module_key == "leads"))
    r = client.post(
        "/api/admin/metadata/fields",
        json={
            "module_key": "leads",
            "section_id": lead_section,
            "api_name": "v2_probe_local_list",
            "label": "Probe",
            "field_type": "picklist",
            "picklist_key": "leads__deal_source",
            "requirement": "Optional",
        },
    )
    check(
        "a local list already serving a field cannot serve a second",
        r.status_code == 409 and r.json().get("detail", {}).get("code") == "PICKLIST_IS_LOCAL",
        r.text[:200],
    )

    open_value = db.execute(
        text("SELECT id FROM picklist_values WHERE picklist_key = 'deals__lead_status' AND key = 'OPEN'")
    ).scalar()
    r = client.patch(f"/api/admin/metadata/picklist-values/{open_value}", json={"active": False})
    check(
        "Open cannot be retired from Deal Status",
        r.status_code == 409 and r.json().get("detail", {}).get("code") == "SYSTEM_VALUE",
        r.text[:200],
    )

    rows = client.get("/api/admin/metadata/conversion-mappings").json()
    pilot = {(r["source_label"], r["target_label"]) for r in rows if r["path"] == "lead_to_deal_pilot" and r["kind"] == "copy"}
    check(
        "Conversion mapping lists the paid pilot's locked rows by their labels",
        ("Pilot Fee", "Contract Value") in pilot
        and all(r["locked"] for r in rows if r["path"] == "lead_to_deal_pilot"),
        str(sorted(pilot)),
    )
    check(
        "…and every row the conversions read",
        {r["target_api_name"] for r in rows if r["path"] == "opportunity_to_deal" and r["kind"] == "copy"}
        == set(R.carry_forward_plan(db, "deals")),
    )

    # Decided 24 Sep 2026: unbuilt modules stay in Administration as they are.
    modules = {m["module_key"] for m in client.get("/api/admin/metadata/modules").json()}
    check(
        "unbuilt modules are still offered, and the Partners children are there",
        {"quotes", "products", "bids_pocs", "activities_docs", "partner_scorecards"} <= modules
        and {"registrations", "conflicts", "partners"} <= modules,
        str(sorted(modules)),
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

    # The pre-Round-7 archive was retired at go-live (migration 0036, 21 Sep
    # 2026): version 1 ships with no earlier history for it to explain.
    archived = db.execute(
        text("SELECT to_regclass('field_metadata_pre_round7') IS NULL")
    ).scalar()
    check("the pre-Round-7 archive is retired", archived is True, str(archived))


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
            case_16_administration_rules,
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

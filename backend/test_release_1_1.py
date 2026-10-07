"""
Release 1.1 — what the head asked for on 6 Oct 2026, checked through the API.

    python run_tests.py test_release_1_1.py     (against the disposable copy)

Chunk A (the server half — the dialogs and the stage bar are screens):
  A1  a Lead made from a registration needs a BD Owner, the refusal names it,
      and the registration links itself once the Lead is saved.
  A2  is test_partner_lifecycle.py's section 1b.

Chunk B (release_1_1_fields_metadata.py, run on this register):
  the old Segment is gone, Theme reads "Segment", an Account holds several
  Segments and must have one, Account Target Phase is gone, Region has Europe,
  and the dashboard's Segment filter reads the Lead's Segment.

Chunk C (release_1_1_location_metadata.py):
  Region -> Country -> State on Accounts and Leads — the server refuses a
  Country outside its Region and a State outside its Country, a Lead's State is
  asked for only when its Country has states, and Import reads a shared state
  name ("Punjab") within the row's own Country.

Chunk D (r11_0002_account_groups, release_1_1_accounts_metadata.py):
  Parent Account, one level deep under the group's head; Make head of group;
  a head with companies can't be deleted; what a group brings in; the
  duplicate check — the same registered name in the same Country refused, a
  similar name asked, answered by joining a group or one click "a different
  company" — on save and rename, and a warning on Import. Partner Tier's new
  choices.

Paid pilot (found 7 Oct 2026): a Paid left hidden by another Agreed Next Step
  makes no Deal, and a pilot marked Paid is asked for its fee and PO date at
  any stage before its Deal is made.
"""

import io
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openpyxl import Workbook  # noqa: E402

from app.database import engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app import account_groups, requirements  # noqa: E402
from app.account_matching import similar  # noqa: E402
from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

# test_support switches the required-field check off for the older scripts;
# this one is about what production does, so it is on.
requirements.ENFORCED = True

client = TestClient(app)
admin = sign_in_as_admin(app)

failed: list[str] = []
created: dict[str, list[str]] = {"leads": [], "registrations": [], "accounts": []}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def detail_of(response) -> dict:
    try:
        body = response.json().get("detail")
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


ACCOUNT = {
    "account_type": ["END_CLIENT"],
    "account_owner": admin.user_id,
    "region": "EUROPE",
    "country": "FR",
    "segments": ["SMART_CITIES", "DATA_CENTERS"],
    "customer_class": "A_STRATEGIC_>$2M",
}

LOCATIONS = json.loads((Path(__file__).parent / "data" / "locations.json").read_text(encoding="utf-8"))
#: A European country ISO lists no states for — its State is never asked for.
NO_STATES = next(c for c in LOCATIONS["regions"]["EUROPE"] if c not in LOCATIONS["states"])


def xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    book.active.title = "Leads"
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def account(name: str, **extra):
    r = client.post("/api/accounts", json={**ACCOUNT, "account_name": f"R11 probe — {name}", **extra})
    if r.status_code == 201:
        created["accounts"].append(r.json()["account_id"])
    return r


try:
    print("=" * 74)
    print("  RELEASE 1.1 — chunks A and B")
    print("=" * 74)

    # ------------------------------------------------------------------ B
    section("B1  The register the app runs on")
    spec = client.get("/api/spec").json()
    fields = spec.get("fields", spec) if isinstance(spec, dict) else spec
    fields = fields if isinstance(fields, list) else []
    by = {(f.get("module"), f.get("api_name")): f for f in fields if isinstance(f, dict)}
    check("the register was read", len(by) > 100, str(len(by)))
    for module in ("leads", "opportunities", "deals", "accounts"):
        check(f"{module}: the old Segment is gone", (module, "segment") not in by)
    for module in ("leads", "opportunities", "deals"):
        f = by.get((module, "theme"), {})
        check(f"{module}: Theme now reads 'Segment'", f.get("label") == "Segment", str(f.get("label")))
    seg = by.get(("accounts", "segments"), {})
    check(
        "accounts: Segment is multi-choice over the same seven choices",
        seg.get("label") == "Segment" and seg.get("type") == "multiselect" and seg.get("picklist") == "theme",
        str({k: seg.get(k) for k in ("label", "type", "picklist")}),
    )
    check("accounts: Account Target Phase is gone", ("accounts", "account_target_phase") not in by)
    picklists = spec.get("picklists", {}) if isinstance(spec, dict) else {}
    check(
        "Region offers Europe",
        "EUROPE" in [v.get("key") for v in picklists.get("region", [])],
        str(picklists.get("region")),
    )

    section("B2  Accounts")
    r = account("no segment", segments=[])
    check("an Account with no Segment is refused", r.status_code == 422, r.text[:200])
    check(
        "…naming Segment",
        {f["api_name"] for f in detail_of(r).get("fields", [])} == {"segments"},
        str(detail_of(r).get("fields")),
    )
    r = account("Europe, two segments")
    check("an Account in Europe with two Segments saves", r.status_code == 201, r.text[:300])
    acc = r.json()["account_id"] if r.status_code == 201 else None
    check("…without Account Target Phase", r.status_code == 201)
    if acc:
        got = client.get(f"/api/accounts/{acc}").json()
        check("…and keeps both Segments", got.get("segments") == ["SMART_CITIES", "DATA_CENTERS"], str(got.get("segments")))
        check("…and its Region", got.get("region") == "EUROPE", str(got.get("region")))
        rows = client.get("/api/accounts", params={"segments": "DATA_CENTERS"}).json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        check("the Accounts list filters on one of the Segments", any(x.get("account_id") == acc for x in rows))
        rows = client.get("/api/accounts", params={"segments": "SMART_TRANSPORT_INFRASTRUCTURE"}).json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        check("…and leaves it out for one it doesn't have", not any(x.get("account_id") == acc for x in rows))

    # ------------------------------------------------------------------ A1
    section("A1  Create lead from a registration")
    partner = account("partner", account_type=["PARTNER_SI"])
    partner_id = partner.json()["account_id"] if partner.status_code == 201 else None
    r = client.post(
        "/api/registrations",
        json={
            "partner": partner_id, "end_client": acc, "project_name": "R11 probe project",
            "currency": "USD", "submitted_date": "2026-10-06", "registration_status": "ACTIVE",
        },
    )
    check("a registration saves", r.status_code == 201, r.text[:300])
    reg = r.json()["id"] if r.status_code == 201 else None
    if reg:
        created["registrations"].append(reg)
    body = {
        "opportunity_name": "R11 probe project", "end_client": acc, "customer_partner_si": partner_id,
        "deal_source": "PARTNER_SOURCED", "partner_deal_registration": reg, "currency": "USD",
        "project_stage": "0_CONNECT",
    }
    r = client.post("/api/leads", json=body)
    check("what Create lead sent before Release 1.1 is refused", r.status_code == 422, r.text[:200])
    check(
        "…and the refusal names BD Owner, which the screen now shows",
        [f.get("label") for f in detail_of(r).get("fields", [])] == ["BD Owner"],
        str(detail_of(r).get("fields")),
    )
    r = client.post("/api/leads", json={**body, "bd_owner": admin.user_id})
    check("with the person pressing it as BD Owner, the lead is created", r.status_code == 201, r.text[:300])
    lead = r.json()["lead_id"] if r.status_code == 201 else None
    if lead:
        created["leads"].append(lead)
        check("…owned by them", r.json().get("bd_owner") == admin.user_id)
        check("…and the registration links to it", client.get(f"/api/registrations/{reg}").json().get("linked_lead") == lead)

    # ------------------------------------------------------------------ B3
    section("B3  Leads and the dashboard")
    if lead:

        def pipeline(**params) -> int:
            return client.get("/api/dashboard", params=params).json()["kpis"]["pipeline"]["count"]

        before = {k: pipeline(segment=k) for k in ("DATA_CENTERS", "DEFENCE_PROTECTED_MARKETS")}
        europe_before = pipeline(region="EUROPE")
        r = client.patch(
            f"/api/leads/{lead}",
            json={"theme": "DATA_CENTERS", "destination_region": "EUROPE", "booking_region": "EUROPE", "estimated_value": 250000},
        )
        check("a Lead takes a Segment and Europe for both regions", r.status_code == 200, r.text[:300])
        got = client.get(f"/api/leads/{lead}").json()
        check("…stored as chosen", got.get("theme") == "DATA_CENTERS" and got.get("booking_region") == "EUROPE", str(got)[:200])
        check(
            "the Account's Segments are untouched — nothing is copied",
            client.get(f"/api/accounts/{acc}").json().get("segments") == ["SMART_CITIES", "DATA_CENTERS"],
        )
        check("the dashboard's Segment filter counts the Lead under its Segment", pipeline(segment="DATA_CENTERS") == before["DATA_CENTERS"] + 1)
        check("…and not under another", pipeline(segment="DEFENCE_PROTECTED_MARKETS") == before["DEFENCE_PROTECTED_MARKETS"])
        check("the Region filter takes Europe", pipeline(region="EUROPE") == europe_before + 1)

    # ------------------------------------------------------------------ C
    section("C1  The maps the app runs on")
    spec = client.get("/api/spec").json()
    deps = spec.get("dependencies", {})
    check("Accounts: Region -> Country -> State", deps.get("accounts", {}).get("country", {}).get("parent") == "region"
          and deps.get("accounts", {}).get("state", {}).get("parent") == "country", str(deps.get("accounts", {}).keys()))
    check("Leads: Destination Region -> Country -> State", deps.get("leads", {}).get("country", {}).get("parent") == "destination_region"
          and deps.get("leads", {}).get("state", {}).get("parent") == "country", str(deps.get("leads", {}).keys()))
    check("India the Region offers India the Country, alone", deps["accounts"]["country"]["map"].get("INDIA") == ["IN"])
    check("UAE offers its seven emirates", len(deps["accounts"]["state"]["map"].get("AE", [])) == 7)
    check("Europe offers France", "FR" in deps["accounts"]["country"]["map"].get("EUROPE", []))
    by = {(f.get("module"), f.get("api_name")): f for f in spec.get("fields", [])}
    check("a Lead's Country is a dropdown now", by.get(("leads", "country"), {}).get("type") == "picklist")
    check("City / State reads City", by.get(("leads", "city_state"), {}).get("label") == "City")
    check("Opportunities show the Lead's State", by.get(("opportunities", "state"), {}).get("value_mode") == "read_through")

    section("C2  Accounts")
    r = account("no country", country=None)
    check("an Account with no Country is refused", r.status_code == 422 and "country" in {f["api_name"] for f in detail_of(r).get("fields", [])}, r.text[:200])
    r = account("Dubai", region="MEA", country="AE", state="AE-DU")
    check("MEA, United Arab Emirates, Dubai saves", r.status_code == 201, r.text[:300])
    dubai = r.json().get("account_id") if r.status_code == 201 else None
    r = account("India in MEA", region="MEA", country="IN")
    check("India under MEA is refused", r.status_code == 422 and detail_of(r).get("code") == "DEPENDENT_CHOICE", r.text[:200])
    check("…in words", detail_of(r).get("message") == "That Country isn't in the Region chosen.", str(detail_of(r).get("message")))
    r = account("Maharashtra in UAE", region="MEA", country="AE", state="IN-MH")
    check("Maharashtra under the UAE is refused", r.status_code == 422 and detail_of(r).get("code") == "DEPENDENT_CHOICE", r.text[:200])
    r = account("no state", region="INDIA", country="IN")
    check("State is optional on an Account", r.status_code == 201, r.text[:200])
    if dubai:
        r = client.patch(f"/api/accounts/{dubai}", json={"region": "APAC"})
        check("moving Dubai's Account to APAC alone is refused — its Country isn't in APAC", r.status_code == 422, r.text[:200])

    section("C3  Leads")
    r = client.post("/api/leads", json={
        "opportunity_name": "R11 probe — location", "end_client": acc, "bd_owner": admin.user_id, "currency": "USD",
        "project_stage": "0_CONNECT", "not_duplicate_reason": "A separate location probe.", "destination_region": "APAC", "country": "FR",
    })
    check("a Lead with France under APAC is refused", r.status_code == 422 and detail_of(r).get("code") == "DEPENDENT_CHOICE", r.text[:200])
    r = client.post("/api/leads", json={
        "opportunity_name": "R11 probe — location", "end_client": acc, "bd_owner": admin.user_id, "currency": "USD",
        "project_stage": "0_CONNECT", "not_duplicate_reason": "A separate location probe.", "destination_region": "EUROPE", "country": "FR",
    })
    check("a Lead in Europe, France, no State yet, saves", r.status_code == 201, r.text[:300])
    loc = r.json().get("lead_id") if r.status_code == 201 else None
    if loc:
        created["leads"].append(loc)
        r = client.patch(f"/api/leads/{loc}", json={"project_stage": "1_DEMO"})
        missing = {f["api_name"] for f in detail_of(r).get("fields", [])}
        check("…leaving Stage 0 asks for its State — France has states", "state" in missing, str(missing))
        r = client.patch(f"/api/leads/{loc}", json={"country": NO_STATES})
        check(f"…moved to {NO_STATES}, which has none", r.status_code == 200, r.text[:200])
        r = client.patch(f"/api/leads/{loc}", json={"project_stage": "1_DEMO"})
        missing = {f["api_name"] for f in detail_of(r).get("fields", [])}
        check("…and then State is never asked for", "state" not in missing, str(missing))

    section("C4  Import reads a shared state name within its Country")
    body = xlsx([
        ["Opportunity Name *", "End Client", "BD Owner", "Destination Region", "Country", "State", "Not a Duplicate — Reason"],
        ["R11 probe — Lahore", f"R11 probe — Europe, two segments", admin.name, "APAC", "Pakistan", "Punjab", "A separate location probe."],
        ["R11 probe — Ludhiana", f"R11 probe — Europe, two segments", admin.name, "India", "India", "Punjab", "A separate location probe."],
        ["R11 probe — wrong", f"R11 probe — Europe, two segments", admin.name, "MEA", "India", None, "A separate location probe."],
    ])
    r = client.post(
        "/api/spreadsheets/leads/import/preview",
        params={"filename": "r11.xlsx"},
        content=body,
        headers={"Content-Type": "application/octet-stream"},
    )
    report = r.json() if r.status_code == 200 else {}
    messages = {e["row"]: " | ".join(e["messages"]) for e in report.get("errors", [])}
    check("the preview answers", r.status_code == 200, r.text[:300])
    check("…Punjab in Pakistan and Punjab in India both read", 2 not in messages and 3 not in messages, str(messages))
    check("…India under MEA is refused, in words", "isn't in the" in messages.get(4, ""), messages.get(4, ""))
    r = client.post(
        "/api/spreadsheets/leads/import",
        params={"filename": "r11.xlsx"},
        content=xlsx([
            ["Opportunity Name *", "End Client", "BD Owner", "Destination Region", "Country", "State", "Not a Duplicate — Reason"],
            ["R11 probe — Lahore", f"R11 probe — Europe, two segments", admin.name, "APAC", "Pakistan", "Punjab", "A separate location probe."],
        ]),
        headers={"Content-Type": "application/octet-stream"},
    )
    check("the Pakistan row imports", r.status_code == 200, r.text[:300])
    if r.status_code == 200:
        rows = client.get("/api/leads", params={"q": "R11 probe — Lahore"}).json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        hit = next((x for x in rows if x.get("opportunity_name") == "R11 probe — Lahore"), {})
        if hit.get("lead_id"):
            created["leads"].append(hit["lead_id"])
        check("…as Pakistan's Punjab, not India's", hit.get("state") == "PK-PB", str(hit.get("state")))

    # ------------------------------------------------------------------ D
    # test_support switches the duplicate check off for the older scripts; on
    # here. Names are made-up words, so no account already in the database is
    # similar to them.
    account_groups.CHECK_DUPLICATES = True

    def company(name: str, region: str, country: str, **extra):
        r = client.post("/api/accounts", json={**ACCOUNT, "account_name": name, "region": region, "country": country, **extra})
        if r.status_code == 201:
            created["accounts"].append(r.json()["account_id"])
        return r

    def parent_of(account_id: str):
        return client.get(f"/api/accounts/{account_id}").json().get("parent_account")

    section("D1  The register")
    spec = client.get("/api/spec").json()
    by = {(f.get("module"), f.get("api_name")): f for f in spec.get("fields", [])}
    parent = by.get(("accounts", "parent_account"), {})
    check("Accounts have Parent Account, a lookup onto Accounts",
          parent.get("type") == "lookup" and parent.get("lookup_target") == "account", str(parent)[:200])
    check("…right after Account Name",
          parent.get("section") == by.get(("accounts", "account_name"), {}).get("section")
          and parent.get("order") == by.get(("accounts", "account_name"), {}).get("order", 0) + 1)
    check("Account Name's tooltip asks for the registered name",
          "registered name" in (by.get(("accounts", "account_name"), {}).get("description") or ""))
    check("Accounts keep no 'different company' reason field", ("accounts", "not_duplicate_reason") not in by)
    tiers = [v.get("label") for v in spec.get("picklists", {}).get("accounts__partner_tier", []) if v.get("active", True)]
    check("Partner Tier: Platinum, Gold, Authorized, Registered, Not a partner",
          tiers == ["Platinum", "Gold", "Authorized", "Registered", "Not a partner"], str(tiers))

    section("D1b  What counts as similar — no names, no word lists")
    check("another legal form of the name", similar("Astrikos Inc", "Astrikos LLC"))
    check("one name is the start of the other", similar("Astrikos Inc", "Astrikos AI Pvt. Ltd."))
    check("a typo apart", similar("Astrikos", "Astrikkos"))
    check("a shared first word alone is not", not similar("Saudi Aramco", "Saudi Electricity Company"))
    check("…nor a shared first two", not similar("Schneider Electric India", "Schneider Electric Paris"))

    section("D2  The duplicate check")
    r = company("Zorvex Holdings Pvt. Ltd.", "INDIA", "IN")
    check("the head saves", r.status_code == 201, r.text[:300])
    head = r.json().get("account_id") if r.status_code == 201 else None

    r = company("Zorvex Inc", "AMERICAS", "US")
    d = detail_of(r)
    check("a similar name is asked about", r.status_code == 422 and d.get("code") == "POSSIBLE_DUPLICATE_ACCOUNT", r.text[:300])
    check("…naming the company", [m.get("account_id") for m in d.get("matches", [])] == [head], str(d.get("matches")))
    check("…in words", d.get("message") == "A company with a similar name is already in Accounts.", str(d.get("message")))
    r = company("Zorvex Inc", "AMERICAS", "US", parent_account=head)
    check("answered 'same group': saved under that group", r.status_code == 201 and r.json().get("parent_account") == head, r.text[:300])
    inc = r.json().get("account_id") if r.status_code == 201 else None

    r = company("ZORVEX INC.", "AMERICAS", "US")
    d = detail_of(r)
    check("the same registered name in the same Country is refused", r.status_code == 409 and d.get("code") == "ACCOUNT_EXISTS", r.text[:300])
    check("…pointing at the one already there", (d.get("existing") or {}).get("account_id") == inc, str(d.get("existing")))
    r = company("Zorvex Inc", "AMERICAS", "US", parent_account=head, not_duplicate_reason="It really is another company.")
    check("…whatever the answer", r.status_code == 409, r.text[:200])

    r = company("Zorvex FZ LLC", "MEA", "AE", parent_account=inc)
    check("picking a member as Parent Account files it under the head", r.status_code == 201 and r.json().get("parent_account") == head, r.text[:300])
    fz = r.json().get("account_id") if r.status_code == 201 else None

    r = company("Zorvex GmbH", "EUROPE", "DE")
    d = detail_of(r)
    check("a different company with a similar name is asked about", d.get("code") == "POSSIBLE_DUPLICATE_ACCOUNT", r.text[:200])
    check("…listing every company of the group it resembles", {m.get("account_id") for m in d.get("matches", [])} == {head, inc, fz}, str(d.get("matches")))
    check("…each with its Region", all(m.get("region") for m in d.get("matches", [])), str(d.get("matches")))
    r = company("Zorvex GmbH", "EUROPE", "DE", different_company=True)
    check("answered 'different company' in one click: saved", r.status_code == 201, r.text[:300])
    analytics = r.json().get("account_id") if r.status_code == 201 else None
    if analytics:
        r = client.patch(f"/api/accounts/{analytics}", json={"account_name": "Zorvex Deutschland GmbH"})
        check("renaming it isn't asked again about the same companies", r.status_code == 200, r.text[:200])
        r = client.patch(f"/api/accounts/{analytics}", json={"account_name": "Zorvex Inc", "country": "US", "region": "AMERICAS"})
        check("renaming it onto a company already there is refused", r.status_code == 409 and detail_of(r).get("code") == "ACCOUNT_EXISTS", r.text[:200])

    r = company("Zorvex Inc", "AMERICAS", "CA")
    check("the same name in another Country is asked, not refused", r.status_code == 422 and detail_of(r).get("code") == "POSSIBLE_DUPLICATE_ACCOUNT", r.text[:200])

    section("D3  Groups")
    if head and inc and fz:
        rows = client.get("/api/accounts", params={"account_name_contains": "Zorvex"}).json()
        size = {x["account_id"]: x.get("group_size") for x in rows}
        check("lists know the group's size", size.get(head) == 3 and size.get(fz) == 3, str(size))
        label = next((x.get("__labels", {}).get("parent_account") for x in rows if x["account_id"] == fz), None)
        check("…and a member's head by name", label == "Zorvex Holdings Pvt. Ltd.", str(label))
        group = [x["account_id"] for x in client.get(f"/api/accounts/{fz}/group").json()["companies"]]
        check("Group companies: the head first, then the rest by name", group == [head, fz, inc], str(group))
        check("a company in no group has none",
              client.get(f"/api/accounts/{analytics}/group").json() == {"companies": [], "total": None} if analytics else True)

        # What the group brings in: one Lead at the FZ, one at Inc with the FZ
        # as its partner — the second names two companies of the group and
        # counts once in the total.
        for name, end_client, partner, value in (
            ("R11 probe — group 1", fz, None, 100000),
            ("R11 probe — group 2", inc, fz, 50000),
        ):
            r = client.post("/api/leads", json={
                "opportunity_name": name, "end_client": end_client, "customer_partner_si": partner,
                "bd_owner": admin.user_id, "currency": "USD", "project_stage": "0_CONNECT",
                "estimated_value": value, "not_duplicate_reason": "A probe.",
            })
            check(f"{name} saves", r.status_code == 201, r.text[:300])
            if r.status_code == 201:
                created["leads"].append(r.json()["lead_id"])
        body = client.get(f"/api/accounts/{fz}/group").json()
        figures = {x["account_id"]: x["figures"] for x in body["companies"]}
        check("the FZ: both pursuits, as End Client and as Partner",
              figures[fz]["pipeline_count"] == 2 and figures[fz]["pipeline_usd"] == 150000, str(figures[fz]))
        check("Inc: its own pursuit", figures[inc]["pipeline_count"] == 1 and figures[inc]["pipeline_usd"] == 50000, str(figures[inc]))
        check("the head: none of its own", figures[head]["pipeline_count"] == 0, str(figures[head]))
        check("the group total counts each pursuit once",
              body["total"]["pipeline_count"] == 2 and body["total"]["pipeline_usd"] == 150000, str(body["total"]))

        r = client.patch(f"/api/accounts/{inc}", json={"parent_account": inc})
        check("a company can't be its own Parent Account", r.status_code == 422 and detail_of(r).get("code") == "PARENT_IS_ITSELF", r.text[:200])
        r = client.patch(f"/api/accounts/{head}", json={"parent_account": fz})
        check("a head can't pick a company of its own group", r.status_code == 422 and detail_of(r).get("code") == "ALREADY_IN_THIS_GROUP", r.text[:200])

        r = client.post(f"/api/accounts/{inc}/make-head")
        check("Make head of group", r.status_code == 200 and r.json().get("parent_account") is None, r.text[:200])
        check("…the old head sits under it", parent_of(head) == inc, str(parent_of(head)))
        check("…and so does the rest of the group", parent_of(fz) == inc, str(parent_of(fz)))
        r = client.post(f"/api/accounts/{inc}/make-head")
        check("…a head can't be made head again", r.status_code == 422, r.text[:200])

        r = client.delete(f"/api/accounts/{inc}")
        check("a head with companies can't be deleted", r.status_code == 409 and detail_of(r).get("code") == "ACCOUNT_HEADS_GROUP", r.text[:200])

        r = company("Quillon Systems", "APAC", "SG")
        q_head = r.json().get("account_id") if r.status_code == 201 else None
        r = company("Quillon Labs", "APAC", "MY", parent_account=q_head)
        q_member = r.json().get("account_id") if r.status_code == 201 else None
        check("a second group forms", bool(q_head and q_member), r.text[:200])
        if q_head and q_member:
            r = client.patch(f"/api/accounts/{q_head}", json={"parent_account": fz})
            check("a head joining another group brings its companies", r.status_code == 200 and parent_of(q_head) == inc and parent_of(q_member) == inc,
                  f"{r.status_code} {parent_of(q_head)} {parent_of(q_member)}")

    section("D4  Import: the same name refused, a similar one a warning")
    requirements.ENFORCED = False
    try:
        sheet = xlsx([
            ["Account Name *", "Account Type", "Region", "Country"],
            ["Zorvex Robotics", "End Client", "Europe", "Germany"],
            ["Zorvex Holdings Private Limited", "End Client", "India", "India"],
        ])
        r = client.post("/api/spreadsheets/accounts/import/preview", params={"filename": "r11.xlsx"}, content=sheet,
                        headers={"Content-Type": "application/octet-stream"})
        report = r.json() if r.status_code == 200 else {}
        messages = {e["row"]: " | ".join(e["messages"]) for e in report.get("errors", [])}
        warnings = {w["row"]: " | ".join(w["messages"]) for w in report.get("warnings", [])}
        check("the preview answers", r.status_code == 200, r.text[:300])
        check("a similar name imports, with a warning naming the others",
              2 not in messages and "similar name" in warnings.get(2, "") and "Zorvex Inc" in warnings.get(2, ""), str((messages.get(2), warnings.get(2))))
        check("the same registered name in the same Country is stopped", "already in ARK" in messages.get(3, ""), messages.get(3, ""))
        template = client.get("/api/spreadsheets/accounts/template")
        check("the sample file no longer asks for a reason", "Not a Duplicate" not in template.content.decode("latin-1"), "")
    finally:
        requirements.ENFORCED = True

    # ------------------------------------------------------------- pilot
    section("P  A paid pilot becomes a Deal only with its commercials")
    account_groups.CHECK_DUPLICATES = False

    def deals_of(lead_id: str) -> list:
        rows = client.get("/api/deals", params={"parent_lead": lead_id}).json()
        return rows if isinstance(rows, list) else rows.get("rows", [])

    r = client.post("/api/leads", json={
        "opportunity_name": "R11 probe — implementation", "end_client": acc, "bd_owner": admin.user_id,
        "currency": "USD", "project_stage": "0_CONNECT", "not_duplicate_reason": "A probe.",
    })
    check("a Lead saves", r.status_code == 201, r.text[:300])
    impl = r.json().get("lead_id") if r.status_code == 201 else None
    if impl:
        created["leads"].append(impl)
        r = client.patch(f"/api/leads/{impl}", json={"agreed_next_step": "IMPLEMENTATION", "pilot_commercial_model": "PAID"})
        check("Implementation with a hidden Paid saves", r.status_code == 200, r.text[:300])
        check("…and stays a Lead", r.json().get("lead_status") != "CONVERTED", str(r.json().get("lead_status")))
        check("…with no Deal made", deals_of(impl) == [], str(deals_of(impl)))

    r = client.post("/api/leads", json={
        "opportunity_name": "R11 probe — paid pilot", "end_client": acc, "bd_owner": admin.user_id,
        "currency": "USD", "project_stage": "0_CONNECT", "not_duplicate_reason": "A probe.",
    })
    pilot = r.json().get("lead_id") if r.status_code == 201 else None
    if pilot:
        created["leads"].append(pilot)
        r = client.patch(f"/api/leads/{pilot}", json={"agreed_next_step": "POC_SCOPING", "pilot_commercial_model": "PAID"})
        missing = {f["api_name"] for f in detail_of(r).get("fields", [])}
        check("marking a pilot Paid at Stage 0 asks for its fee and PO date",
              r.status_code == 422 and {"pilot_fee", "pilot_po_received_date"} <= missing, f"{r.status_code} {missing}")
        check("…in words", detail_of(r).get("message") == "Fill in the pilot's details before it becomes a Deal.", str(detail_of(r).get("message")))
        check("…and makes no Deal", deals_of(pilot) == [], str(deals_of(pilot)))
        r = client.patch(f"/api/leads/{pilot}", json={
            "agreed_next_step": "POC_SCOPING", "pilot_commercial_model": "PAID",
            "pilot_fee": 40000, "pilot_po_received_date": "2026-10-05",
        })
        missing = {f["api_name"] for f in detail_of(r).get("fields", [])}
        check("with them it is no longer the pilot's details that are asked",
              not ({"pilot_fee", "pilot_po_received_date"} & missing), f"{r.status_code} {missing}")

finally:
    section("Cleanup")
    account_groups.CHECK_DUPLICATES = True
    # Groups first: a head with companies can't be deleted.
    for record_id in created["accounts"]:
        client.patch(f"/api/accounts/{record_id}", json={"parent_account": None})
    for collection in ("leads", "registrations", "accounts"):
        for record_id in reversed(created[collection]):
            r = client.delete(f"/api/{collection}/{record_id}")
            if r.status_code not in (200, 204, 404):
                print(f"  could not delete {collection}/{record_id}: {r.status_code}")

print()
if failed:
    print(f"{len(failed)} FAILED")
    for line in failed:
        print(f"  - {line}")
    sys.exit(1)
print("all passed")

"""
Setup, step 4e (5 Oct 2026): Setup shows every field where the record does.

    python run_tests.py test_setup_4e.py

  * The register after setup_step4e_metadata.py: attached fields filed where
    they draw; no Conditional requirement left; no written formula sentence,
    the day counters' moved into their tooltip; the two stage-move reasons
    marked as asked at a stage move, and never demanded of a save.
  * Required and its rule: a required field's rule IS its show-when rule.
  * Attaching moves a field to its anchor's section; moving it alone detaches.
  * The layout editor's Save carries "Show under / beside" and width: same
    section only, no loops, left-out keys kept, a field moved away detached.
  * Where-used, before Remove Field: rules, formulas, attached fields, later
    modules, Conversion Mapping, Reasons & Justifications.
  * A field with its own column keeps a compatible type.
  * The draft says which module, section and field a pending change touches.
  * The section and field reorder routes are gone.
"""

import sys

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from app import requirements as REQ  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConversionMapping, FieldDefinition, FieldPlacement, Section  # noqa: E402
from test_support import RegisterGuard, sign_in_as_admin  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "/api/admin/metadata"
client = TestClient(app)
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


admin = sign_in_as_admin(app)


def fields_of(module: str, status: str = "active"):
    return client.get(f"{BASE}/fields", params={"module": module, "status": status}).json()


def field(module: str, api_name: str):
    return next((f for f in fields_of(module, "all") if f["api_name"] == api_name and f["status"] == "active"), None)


def state(module: str = "leads"):
    sections = sorted(
        (s for s in client.get(f"{BASE}/sections", params={"module": module}).json() if s["active"]),
        key=lambda s: (s["sort_order"], s["id"]),
    )
    rows = sorted(fields_of(module), key=lambda f: (f["sort_order"] or 0, f["placement_id"]))
    return sections, rows


def payload(sections, rows, extra=None):
    extra = extra or {}
    return {
        "sections": [{"id": s["id"], "key": f"s{s['id']}", "label": s["label"]} for s in sections],
        "placements": [
            {"placement_id": f["placement_id"], "section": f"s{f['section_id']}", **extra.get(f["placement_id"], {})}
            for f in rows
        ],
        "required": {},
    }


layout_id = client.get(f"{BASE}/layouts", params={"module": "leads"}).json()[0]["id"]

with RegisterGuard() as guard:
    print("\n1  The register after setup_step4e_metadata.py")
    with SessionLocal() as db:
        labels = {s.id: s.label for s in db.scalars(select(Section))}
        rows = list(db.scalars(select(FieldPlacement).where(FieldPlacement.status == "active")))
        by_key = {(p.module_key, p.api_name): p for p in rows}
        for module in ("leads", "opportunities", "deals"):
            for api_name, home in (
                ("on_hold_reason", "RECORD STATE"),
                ("closed_lost_reason_code", "RECORD STATE"),
                ("probability_override_justification", "Health & Forecast"),
            ):
                p = by_key.get((module, api_name))
                check(f"{module}.{api_name} is filed where it draws ({home})", p is not None and labels[p.section_id] == home, p and labels[p.section_id])
        check("no Conditional requirement is left", not [p for p in rows if p.requirement == "Conditional"])
        demanded_by_rule = [p for p in rows if p.condition]
        check(
            "every field with a rule is required, and its rule is its show-when rule",
            all(p.requirement == "Mandatory" and p.condition == p.visibility_condition for p in demanded_by_rule),
            str([(p.module_key, p.api_name, p.requirement) for p in demanded_by_rule if p.requirement != "Mandatory"][:3]),
        )
        sentences = db.scalar(select(FieldDefinition).where(FieldDefinition.computed_formula.is_not(None)))
        check("no written formula sentence is left", sentences is None)
        counter = db.scalar(select(FieldDefinition).where(FieldDefinition.scope_key == "leads", FieldDefinition.api_name == "days_since_last_update"))
        check("…a day counter's moved into its tooltip", "Worked out as: Today − Modified Date." in (counter.description or ""), counter.description)
        marked = sorted((p.module_key, p.api_name) for p in rows if p.asked_at_stage_move)
        check(
            "the two stage-move reasons are marked, on all three modules",
            marked == sorted((m, n) for m in ("leads", "opportunities", "deals") for n in ("stage_skip_reason", "stage_reversal_reason")),
            str(marked),
        )

    spec = client.get("/api/spec").json()
    skip = next(f for f in spec["fields"] if f["module"] == "leads" and f["api_name"] == "stage_skip_reason")
    check("the published register says so", skip.get("asked_at_stage_move") is True)
    check("…and a save never demands it", REQ._applies({**skip, "requirement": "Mandatory"}, "leads") is False)
    plain = next(f for f in spec["fields"] if f["module"] == "leads" and f["api_name"] == "opportunity_name")
    check("a field not asked at a stage move carries no key for it", "asked_at_stage_move" not in plain)

    print("\n2  Required, and when")
    region = field("leads", "destination_region")
    rule = "deal_source == 'Partner-sourced'"
    r = client.patch(f"{BASE}/placements/{region['placement_id']}", json={"requirement": "Mandatory", "visibility_condition": rule})
    check("a required field shown by a rule is demanded by the same rule", r.status_code == 200 and r.json()["condition"] == rule, r.text[:200])
    r = client.patch(f"{BASE}/placements/{region['placement_id']}", json={"requirement": "Optional"})
    check("…and an optional one by none", r.status_code == 200 and r.json()["condition"] is None, r.text[:200])

    print("\n3  An attached field lives where it draws")
    city = field("leads", "city_state")
    status_field = field("leads", "lead_status")
    r = client.patch(f"{BASE}/placements/{city['placement_id']}", json={"anchor_field": "lead_status"})
    check("attaching moves it into its anchor's section", r.status_code == 200 and r.json()["section_id"] == status_field["section_id"], r.text[:200])
    stage0 = next(s for s in state()[0] if s["label"].startswith("STAGE 0"))
    r = client.patch(f"{BASE}/placements/{city['placement_id']}", json={"section_id": stage0["id"]})
    check("moving it on its own detaches it", r.status_code == 200 and r.json()["anchor_field"] is None and r.json()["section_id"] == stage0["id"], r.text[:200])

    print("\n4  The layout editor's Save carries where a field draws")
    sections, rows = state()
    by = {f["api_name"]: f for f in rows}
    country, city = by["country"], by["city_state"]
    r = client.put(
        f"{BASE}/layouts/{layout_id}",
        json=payload(sections, rows, {city["placement_id"]: {"anchor": country["placement_id"], "anchor_position": "beside"}, country["placement_id"]: {"span": "full"}}),
    )
    city, country = field("leads", "city_state"), field("leads", "country")
    check("Show beside is saved", r.status_code == 200 and city["anchor_field"] == "country" and city["anchor_position"] == "beside", r.text[:200])
    check("…and Full width", country["layout_span"] == "full", str(country["layout_span"]))

    sections, rows = state()
    r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, rows))
    check("a Save that does not mention them keeps them", r.status_code == 200 and field("leads", "city_state")["anchor_field"] == "country", r.text[:200])

    sections, rows = state()
    by = {f["api_name"]: f for f in rows}
    r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, rows, {by["country"]["placement_id"]: {"anchor": by["city_state"]["placement_id"]}}))
    check("a loop is refused", r.status_code == 422 and code_of(r) == "ANCHOR_LOOP", r.text[:200])
    elsewhere = next(f for f in rows if f["section_id"] != by["city_state"]["section_id"])
    r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, rows, {by["city_state"]["placement_id"]: {"anchor": elsewhere["placement_id"]}}))
    check("an anchor in another section is refused", r.status_code == 422 and code_of(r) == "LAYOUT_OUT_OF_DATE", r.text[:200])

    aging = next(s for s in sections if s["label"] == "Aging")
    moved = [dict(f, section_id=aging["id"]) if f["api_name"] == "city_state" else f for f in rows]
    r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, moved))
    check("a field moved away from its anchor is detached", r.status_code == 200 and field("leads", "city_state")["anchor_field"] is None, r.text[:200])

    print("\n5  What reads a field, before Remove Field")
    usage = client.get(f"{BASE}/placements/{status_field['placement_id']}/usage").json()
    kinds = {u["kind"] for u in usage}
    check("Status: the reasons attached under it", "attached" in kinds, str(usage[:3]))
    check("…and the rules that read it", "rule" in kinds, str(kinds))
    years = field("opportunities", "contract_years")
    usage = client.get(f"{BASE}/placements/{years['placement_id']}/usage").json()
    check("Contract Years: the formulas worked out from it", any(u["kind"] == "formula" and "Total Value" in u["text"] for u in usage), str(usage[:3]))
    skip = field("leads", "stage_skip_reason")
    usage = client.get(f"{BASE}/placements/{skip['placement_id']}/usage").json()
    check("Stage Skip Reason: Reasons & Justifications", any(u["kind"] == "reasons" for u in usage), str(usage))
    with SessionLocal() as db:
        mapping = db.scalar(select(ConversionMapping).where(ConversionMapping.active.is_(True), ConversionMapping.source_module == "leads"))
    if mapping is not None:
        source = field("leads", mapping.source_api_name)
        usage = client.get(f"{BASE}/placements/{source['placement_id']}/usage").json() if source else []
        check("a mapped field: Conversion copies it", any(u["kind"] == "conversion" for u in usage), str(usage[:3]))
    text_words = " ".join(u["text"] for u in client.get(f"{BASE}/placements/{status_field['placement_id']}/usage").json())
    check("…said without system names", "lead_status" not in text_words and "__" not in text_words, text_words[:200])

    print("\n6  A field with its own column keeps a compatible type")
    name = field("leads", "opportunity_name")
    r = client.patch(f"{BASE}/fields/{name['definition_id']}", json={"field_type": "number"})
    check("Text to Number is refused", r.status_code == 422 and code_of(r) == "FIELD_TYPE_FIXED", r.text[:200])
    r = client.patch(f"{BASE}/fields/{name['definition_id']}", json={"field_type": "longtext"})
    check("Text to Long Text is allowed", r.status_code == 200, r.text[:200])
    client.patch(f"{BASE}/fields/{name['definition_id']}", json={"field_type": "text"})

    print("\n7  The draft says where each pending change is")
    region = field("leads", "destination_region")
    client.patch(f"{BASE}/placements/{region['placement_id']}", json={"requirement": "Mandatory"})
    items = client.get(f"{BASE}/draft").json()["items"]
    mine = [i for i in items if i["kind"] == "field" and i["module"] == "leads" and i["name"] == "destination_region"]
    check("a field change names its module, section and field", bool(mine) and mine[0]["section"], str(items[:3]))
    check("…and its sentence is the one the banner lists", bool(mine) and mine[0]["text"] in client.get(f"{BASE}/draft").json()["changes"])

    print("\n8  One way to arrange a layout")
    check("the section reorder route is gone", client.post(f"{BASE}/sections/reorder", json={"ids": []}).status_code in (404, 405))
    check("the field reorder routes are gone", client.post(f"{BASE}/placements/reorder", json={"ids": []}).status_code in (404, 405, 422))

print(f"\nRegisterGuard: {len(guard.repairs)} repair(s)")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")

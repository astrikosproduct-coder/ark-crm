"""
Setup, step 4c (1 Oct 2026): the layout editor saves a whole session at once.

    python run_tests.py test_setup_layout.py

PUT /api/admin/metadata/layouts/{id} takes the arrangement the editor ended
with — every section kept, in order; every field on the form, in order — and
applies it in ONE transaction:

  * an unchanged arrangement changes nothing;
  * a field moved into another section takes that section's stage with it
    (into STAGE 1 → capture stage 1; into a non-stage section → none);
  * a new section can be made between two others, and fields moved into it;
  * a field left out goes to Unused Items, stamped with the signed-in user;
    listed again, it comes back;
  * Mark as required moves Mandatory ↔ Optional only, and a refusal anywhere
    leaves everything as it was;
  * section names stay unique, and a stage section keeps its STAGE number;
  * two sections can swap names in one save;
  * a deleted section is deleted, or switched off while an Unused Item still
    points at it.

Placements are put back by RegisterGuard; sections by the teardown.
"""

import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from app.main import app  # noqa: E402
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
layout_id = client.get(f"{BASE}/layouts", params={"module": "leads"}).json()[0]["id"]


def state():
    """The leads layout as the editor would load it: sections and fields in order."""
    sections = sorted(
        (s for s in client.get(f"{BASE}/sections", params={"module": "leads"}).json() if s["active"]),
        key=lambda s: (s["sort_order"], s["id"]),
    )
    fields = sorted(
        client.get(f"{BASE}/fields", params={"module": "leads", "status": "active"}).json(),
        key=lambda f: (f["sort_order"] or 0, f["placement_id"]),
    )
    return sections, fields


def payload(sections, fields, required=None):
    return {
        "sections": [{"id": s["id"], "key": f"s{s['id']}", "label": s["label"]} for s in sections],
        "placements": [{"placement_id": f["placement_id"], "section": f"s{f['section_id']}"} for f in fields],
        "required": required or {},
    }


def field(api_name):
    return next(
        f for f in client.get(f"{BASE}/fields", params={"module": "leads", "status": "all"}).json()
        if f["api_name"] == api_name
    )


with SessionLocal() as db:
    original_sections = db.execute(
        text("SELECT id, label, sort_order, active FROM sections WHERE module_key = 'leads'")
    ).all()

print("=" * 74)
print("  SETUP — the layout editor saves a session at once")
print("=" * 74)

try:
    with RegisterGuard() as guard:
        sections, fields = state()
        stage0 = next(s for s in sections if s["label"].startswith("STAGE 0"))
        stage1 = next(s for s in sections if s["label"].startswith("STAGE 1"))
        aging = next(s for s in sections if s["label"] == "Aging")

        print("\n1  Nothing changed, nothing changes")
        before = [(f["placement_id"], f["section_id"], f["capture_stage"], f["requirement"]) for f in fields]
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, fields))
        check("an unchanged layout saves", r.status_code == 200, r.text[:300])
        _, after_fields = state()
        after = [(f["placement_id"], f["section_id"], f["capture_stage"], f["requirement"]) for f in after_fields]
        check("…and every field is where it was", sorted(before) == sorted(after))

        print("\n2  A field takes its new section's stage")
        moved = [dict(f, section_id=aging["id"]) if f["api_name"] == "country" else f for f in fields]
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, moved))
        country = field("country")
        check("moved into Aging", r.status_code == 200 and country["section_id"] == aging["id"], r.text[:200])
        check("…and its stage is cleared", country["capture_stage"] is None, str(country["capture_stage"]))
        moved = [dict(f, section_id=stage1["id"]) if f["api_name"] == "country" else f for f in fields]
        client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, moved))
        check("moved into STAGE 1, it is a Stage 1 field", field("country")["capture_stage"] == 1)

        print("\n3  A new section, between two others")
        sections, fields = state()
        body = payload(sections, fields)
        at = next(i for i, s in enumerate(body["sections"]) if s["id"] == stage1["id"])
        body["sections"].insert(at, {"id": None, "key": "new-1", "label": "STAGE 1 — Zz Notes"})
        for p in body["placements"]:
            if p["placement_id"] == field("country")["placement_id"]:
                p["section"] = "new-1"
        r = client.put(f"{BASE}/layouts/{layout_id}", json=body)
        check("saved", r.status_code == 200, r.text[:300])
        sections2, _ = state()
        new = next((s for s in sections2 if s["label"] == "STAGE 1 — Zz Notes"), None)
        names = [s["label"] for s in sections2]
        check("the section exists", new is not None)
        check(
            "…just before STAGE 1",
            new is not None and names.index(new["label"]) + 1 == names.index(stage1["label"]),
            str(names),
        )
        check("…with the field in it", new is not None and field("country")["section_id"] == new["id"])

        print("\n4  Unused Items, both ways")
        sections, fields = state()
        without = [f for f in fields if f["api_name"] != "city_state"]
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, without))
        city = field("city_state")
        check("a field left out goes to Unused Items", r.status_code == 200 and city["status"] == "deleted", r.text[:200])
        check("…stamped with the signed-in user", city["deleted_by"] == admin.user_id, str(city["deleted_by"]))
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, without + [dict(city, section_id=aging["id"])]))
        city = field("city_state")
        check("listed again, it comes back", r.status_code == 200 and city["status"] == "active", r.text[:200])
        check("…into the section it was dropped in", city["section_id"] == aging["id"])

        print("\n5  Mark as required, and all-or-nothing")
        sections, fields = state()
        dest = field("destination_region")
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, fields, {dest["placement_id"]: True}))
        check("an Optional field is made required", r.status_code == 200 and field("destination_region")["requirement"] == "Mandatory", r.text[:200])
        conditional = field("partner_deal_registration")
        moved = [dict(f, section_id=aging["id"]) if f["api_name"] == "booking_region" else f for f in fields]
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(sections, moved, {conditional["placement_id"]: True}))
        check("a field with its own rule is refused", r.status_code == 422 and code_of(r) == "REQUIREMENT_NOT_TOGGLED", r.text[:200])
        check("…and the move in the same save did not happen", field("booking_region")["section_id"] != aging["id"])

        print("\n6  Section names")
        body = payload(sections, fields)
        body["sections"].append({"id": None, "key": "new-x", "label": "aging"})
        r = client.put(f"{BASE}/layouts/{layout_id}", json=body)
        check("a name already used is refused", r.status_code == 422 and code_of(r) == "SECTION_NAME_TAKEN", r.text[:200])
        body = payload(sections, fields)
        for s in body["sections"]:
            if s["id"] == stage0["id"]:
                s["label"] = "Connect"
        r = client.put(f"{BASE}/layouts/{layout_id}", json=body)
        check("a stage section cannot lose its stage", r.status_code == 422 and code_of(r) == "SECTION_STAGE_FIXED", r.text[:200])
        body = payload(sections, fields)
        system = next(s for s in sections if s["label"] == "SYSTEM")
        for s in body["sections"]:
            if s["id"] == aging["id"]:
                s["label"] = "SYSTEM"
            elif s["id"] == system["id"]:
                s["label"] = "Aging"
        r = client.put(f"{BASE}/layouts/{layout_id}", json=body)
        swapped = {s["id"]: s["label"] for s in state()[0]}
        check("two sections swap names in one save", r.status_code == 200 and swapped[aging["id"]] == "SYSTEM" and swapped[system["id"]] == "Aging", r.text[:200])
        body = payload(*state())
        for s in body["sections"]:
            if s["id"] == aging["id"]:
                s["label"] = "Aging"
            elif s["id"] == system["id"]:
                s["label"] = "SYSTEM"
        client.put(f"{BASE}/layouts/{layout_id}", json=body)

        print("\n7  Deleting sections")
        sections, fields = state()
        notes = next(s for s in sections if s["label"] == "STAGE 1 — Zz Notes")
        kept = [s for s in sections if s["id"] != notes["id"]]
        moved = [dict(f, section_id=stage1["id"]) if f["section_id"] == notes["id"] else f for f in fields]
        r = client.put(f"{BASE}/layouts/{layout_id}", json=payload(kept, moved))
        with SessionLocal() as db:
            gone = db.execute(text("SELECT 1 FROM sections WHERE id = :i"), {"i": notes["id"]}).first() is None
        check("an emptied section is deleted", r.status_code == 200 and gone, r.text[:200])

        body = payload(*state())
        body["sections"].append({"id": None, "key": "new-2", "label": "Zz Scratch"})
        for p in body["placements"]:
            if p["placement_id"] == field("country")["placement_id"]:
                p["section"] = "new-2"
        client.put(f"{BASE}/layouts/{layout_id}", json=body)
        scratch = next(s for s in state()[0] if s["label"] == "Zz Scratch")
        sections, fields = state()
        r = client.put(
            f"{BASE}/layouts/{layout_id}",
            json=payload([s for s in sections if s["id"] != scratch["id"]], [f for f in fields if f["section_id"] != scratch["id"]]),
        )
        with SessionLocal() as db:
            row = db.execute(text("SELECT active FROM sections WHERE id = :i"), {"i": scratch["id"]}).first()
        check("a section an Unused Item remembers is switched off, not deleted", r.status_code == 200 and row is not None and row[0] is False, f"{r.text[:150]} {row}")

        print("\n8  An out-of-date editor is refused")
        sections, fields = state()
        body = payload(sections, fields)
        body["placements"].append({"placement_id": 99999999, "section": f"s{aging['id']}"})
        r = client.put(f"{BASE}/layouts/{layout_id}", json=body)
        check("an unknown field is refused", r.status_code == 422 and code_of(r) == "LAYOUT_OUT_OF_DATE", r.text[:200])

    print(f"\nRegisterGuard: {len(guard.repairs)} repair(s)")

finally:
    with SessionLocal() as db:
        ids = {row.id for row in original_sections}
        # Placements are back in their own sections (RegisterGuard), so what the
        # test made can go, and what it renamed or moved is put back.
        db.execute(
            text("DELETE FROM sections WHERE module_key = 'leads' AND NOT (id = ANY(:ids))"),
            {"ids": list(ids)},
        )
        for row in original_sections:
            db.execute(text("UPDATE sections SET label = :l || '__tmp' WHERE id = :i"), {"l": row.label, "i": row.id})
        for row in original_sections:
            db.execute(
                text("UPDATE sections SET label = :l, sort_order = :o, active = :a WHERE id = :i"),
                {"l": row.label, "o": row.sort_order, "a": row.active, "i": row.id},
            )
        db.commit()
    print("Cleanup done")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")

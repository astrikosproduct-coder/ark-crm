"""
End-to-end test of the Round-6 metadata layer.

Run:  python test_metadata_round6.py

Walks the twenty checks Round 6 has to pass, in order, against the real
database and the real spec files, through the real API. Not a unit test suite
— a rehearsal of what an admin actually does, because the things most worth
proving here are the ones that only show up end to end:

    * a deleted field disappears from the CRM
    * the business column and its VALUES survive that deletion
    * restoring the field brings the data back into view
    * a bad draft cannot become the published configuration
    * a published version cannot be edited
    * an old version can be republished

THE LICENCE MODEL SCENARIO
---------------------------
Checks 4 to 10 use opportunities.licence_model, which is the exact case the
Round-6 brief names: "Opportunity -> Licence Model". A real Opportunity row is
created carrying a real value, the field is deleted through the Administration
API, and the test then asserts against information_schema and against the row
itself that PostgreSQL still holds both. That is the assertion the whole
deletion model rests on, so it is made against the database rather than
against the API's own account of itself.

WHAT IT TOUCHES, AND WHAT IT PUTS BACK
---------------------------------------
It publishes, so it writes frontend/spec/*.json. It records their checksums
first and asserts at the end that all three are byte-identical to how they
started. Its own Opportunity row is deleted in the teardown, and every metadata
edit it makes is reversed before it finishes.
"""

import hashlib
import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine

# Before app.main is imported: importing it runs create_all(), and echo=True
# turns that into 40 lines of catalogue queries before the first check prints.
engine.echo = False

from test_db import require_test_database  # noqa: E402

# This test writes. Refuse to run against the database the prototype is
# demonstrated from — the copy is made by run_tests.py. See test_db.py.
require_test_database()

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402
from app.metadata_spec import (  # noqa: E402
    FIELDS_JSON,
    PICKLISTS_JSON,
    SPEC_DIR,
    STAGES_JSON,
)
from app.models import Opportunity  # noqa: E402

BASE = "/api/admin/metadata"
client = TestClient(app)

# Every route is mounted behind require_access / require_administration, which read a
# signed-in user from the session cookie. A TestClient has none and cannot get
# one — sign-in goes through Entra. Without this, every request here returns
# 401 and the suite asserts nothing. See test_support.py.
sign_in_as_admin(app)


passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name}  {detail}")


def spec_hashes() -> dict[str, str]:
    return {
        name: hashlib.md5((SPEC_DIR / name).read_bytes()).hexdigest()
        # module_split.json included: a publish regenerates its structural
        # blocks, so it has to come back byte-identical like the other three.
        for name in (FIELDS_JSON, PICKLISTS_JSON, STAGES_JSON, "module_split.json")
    }


def spec_fields() -> list[dict]:
    import json

    return json.loads((SPEC_DIR / FIELDS_JSON).read_text(encoding="utf-8"))


def api_names_in_spec() -> set[str]:
    return {f"{r['module']}.{r['api_name']}" for r in spec_fields()}


def sql(statement: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(statement), params).fetchall()


def main() -> int:
    print("Round 6 — end-to-end\n")
    before = spec_hashes()

    # ---------------------------------------------------------------
    # A business record carrying a real value in the column whose field
    # this test is about to delete.
    # ---------------------------------------------------------------
    opportunity_id = "OPP-R6TEST"
    with SessionLocal() as db:
        # Through the ORM rather than raw SQL: Opportunity declares Python-side
        # defaults for a dozen NOT NULL booleans, and restating them here would
        # mean this fixture breaking every time that model gains a column.
        db.execute(
            text("DELETE FROM opportunities WHERE opportunity_id = :id"),
            {"id": opportunity_id},
        )
        db.add(Opportunity(opportunity_id=opportunity_id, licence_model="PERPETUAL"))
        db.commit()

    # Metadata v2: licence_model is one field_definitions row owned by
    # Opportunities (scope 'opportunities'; origin_module still 'leads', the
    # register sheet it was historically filed on) with ONE placement, on opportunities — the module carry='moved'
    # actually routes it to. Delete/restore act on the DEFINITION; the
    # required-toggle acts on the PLACEMENT, because that is what is checked
    # against the opportunities.licence_model column below.
    licence_definition = sql(
        "SELECT id FROM field_definitions WHERE api_name = 'licence_model' "
        "AND scope_key = 'opportunities'"
    )
    licence_definition_id = licence_definition[0][0]
    licence_placement = sql(
        "SELECT id FROM field_placements WHERE api_name = 'licence_model' "
        "AND module_key = 'opportunities' AND definition_id = :d",
        d=licence_definition_id,
    )
    licence_placement_id = licence_placement[0][0]

    # Leftovers from a run that crashed before its own teardown ran.
    # Placements first: the FK from field_placements to field_definitions
    # is RESTRICT.
    with SessionLocal() as db:
        db.execute(text("DELETE FROM field_placements WHERE api_name = 'r6_test_field'"))
        db.execute(text("DELETE FROM field_definitions WHERE api_name = 'r6_test_field'"))
        db.execute(text("DELETE FROM picklist_values WHERE picklist_key = 'r6_test_picklist'"))
        db.execute(text("DELETE FROM picklists WHERE picklist_key = 'r6_test_picklist'"))
        db.commit()

    # ---------------------------------------------------------- 15 (first)
    # Publish the untouched draft, so later checks have a baseline version
    # to diff and roll back to.
    response = client.post(f"{BASE}/publish", json={"note": "Round 6 baseline"})
    check("15  publish metadata", response.status_code == 200, response.text[:300])
    baseline_version = (
        response.json()["version"]["version_no"] if response.status_code == 200 else None
    )

    # ------------------------------------------------------------------ 1
    section = client.get(f"{BASE}/sections", params={"module": "leads"}).json()[0]
    created = client.post(
        f"{BASE}/fields",
        json={
            "module_key": "leads",
            "section_id": section["id"],
            "api_name": "r6_test_field",
            "label": "R6 Test Field",
            "field_type": "text",
            "requirement": "Optional",
            "description": "Created by test_metadata_round6.py",
        },
    )
    check("1   create field", created.status_code == 201, created.text[:300])
    # `id` is the PLACEMENT (used for the /required toggle in check 3 and the
    # placement-id comparison in check 20); `definition_id` is the canonical
    # field (used for the definition-level edits in checks 2 and 18).
    new_field_id = created.json()["id"] if created.status_code == 201 else None
    new_definition_id = created.json()["definition_id"] if created.status_code == 201 else None

    # ------------------------------------------------------------------ 2
    edited = client.patch(
        f"{BASE}/fields/{new_definition_id}", json={"label": "R6 Test Field (edited)"}
    )
    check(
        "2   edit field",
        edited.status_code == 200
        and edited.json()["definition_label"] == "R6 Test Field (edited)",
        edited.text[:200],
    )

    # ------------------------------------------------------------------ 3
    on = client.patch(f"{BASE}/fields/{new_field_id}/required", json={"required": True})
    off = client.patch(f"{BASE}/fields/{new_field_id}/required", json={"required": False})
    check(
        "3   toggle required on and off",
        on.json()["requirement"] == "Mandatory"
        and on.json()["required"] is True
        and off.json()["requirement"] == "Optional"
        and off.json()["required"] is False,
        f"{on.text[:120]} / {off.text[:120]}",
    )

    # A required toggle must never reach the business schema.
    nullable = sql(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'opportunities' AND column_name = 'licence_model'"
    )
    client.patch(
        f"{BASE}/placements/{licence_placement_id}/required", json={"required": True}
    )
    still_nullable = sql(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'opportunities' AND column_name = 'licence_model'"
    )
    check(
        "3b  required does NOT make the business column NOT NULL",
        nullable[0][0] == "YES" and still_nullable[0][0] == "YES",
        f"{nullable} -> {still_nullable}",
    )
    client.patch(
        f"{BASE}/placements/{licence_placement_id}/required", json={"required": False}
    )

    # ------------------------------------------------------------------ 4
    # DELETE /fields/{definition_id} deletes the field EVERYWHERE. licence_model
    # has exactly one placement (opportunities), so "everywhere" and "remove
    # from opportunities" coincide here — this is still the Round-6 scenario,
    # deleting the field entirely.
    deleted = client.request("DELETE", f"{BASE}/fields/{licence_definition_id}", json={})
    check(
        "4   delete field (licence_model)",
        deleted.status_code == 200 and deleted.json()["definition_status"] == "deleted",
        deleted.text[:300],
    )

    # ------------------------------------------------------------------ 5
    client.post(f"{BASE}/publish", json={"note": "Round 6 test — licence_model deleted"})
    # Round 7: fields.json's `module` column is the PLACEMENT's module, not
    # the register sheet the field was historically filed on. licence_model's
    # placement is on opportunities — Administration -> Opportunities ->
    # Fields is the exact case CLAUDE.md names — so its live key in the spec
    # is "opportunities.licence_model", not "leads.licence_model".
    check(
        "5   deleted field disappears from the CRM spec",
        "opportunities.licence_model" not in api_names_in_spec(),
        "still present in fields.json",
    )

    # ------------------------------------------------------------------ 6
    column = sql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'opportunities' AND column_name = 'licence_model'"
    )
    check("6   business column still exists", len(column) == 1, str(column))

    # ------------------------------------------------------------------ 7
    value = sql(
        "SELECT licence_model FROM opportunities WHERE opportunity_id = :id",
        id=opportunity_id,
    )
    check(
        "7   existing field values still present",
        value and value[0][0] == "PERPETUAL",
        str(value),
    )

    # ------------------------------------------------------------------ 8
    restored = client.post(f"{BASE}/fields/{licence_definition_id}/restore")
    check(
        "8   restore field",
        restored.status_code == 200 and restored.json()["definition_status"] == "active",
        restored.text[:300],
    )

    # ------------------------------------------------------------------ 9
    client.post(f"{BASE}/publish", json={"note": "Round 6 test — licence_model restored"})
    check(
        "9   restored field reappears in the CRM spec",
        "opportunities.licence_model" in api_names_in_spec(),
        "missing from fields.json",
    )

    # ----------------------------------------------------------------- 10
    value = sql(
        "SELECT licence_model FROM opportunities WHERE opportunity_id = :id",
        id=opportunity_id,
    )
    check(
        "10  previous data visible again after restore",
        value and value[0][0] == "PERPETUAL",
        str(value),
    )

    # ----------------------------------------------------------------- 11
    picklist = client.post(
        f"{BASE}/picklists",
        json={"picklist_key": "r6_test_picklist", "label": "R6 Test Picklist"},
    )
    renamed = client.patch(
        f"{BASE}/picklists/r6_test_picklist", json={"label": "R6 Test Picklist (edited)"}
    )
    check(
        "11  create and edit picklist",
        picklist.status_code == 201 and renamed.status_code == 200,
        f"{picklist.text[:150]} / {renamed.text[:150]}",
    )

    # ----------------------------------------------------------------- 12
    first = client.post(
        f"{BASE}/picklist-values",
        json={"picklist_key": "r6_test_picklist", "key": "ALPHA", "label": "Alpha"},
    )
    second = client.post(
        f"{BASE}/picklist-values",
        json={"picklist_key": "r6_test_picklist", "key": "BETA", "label": "Beta"},
    )
    reordered = client.post(
        f"{BASE}/picklist-values/reorder",
        json={"ids": [second.json()["id"], first.json()["id"]]},
    )
    deactivated = client.patch(
        f"{BASE}/picklist-values/{first.json()['id']}", json={"active": False}
    )
    order_ok = [v["key"] for v in reordered.json()] == ["BETA", "ALPHA"]
    check(
        "12  create, reorder and deactivate picklist values",
        first.status_code == 201
        and second.status_code == 201
        and order_ok
        and deactivated.json()["active"] is False,
        f"order={[v['key'] for v in reordered.json()]}",
    )

    # ----------------------------------------------------------------- 13
    section_edit = client.patch(
        f"{BASE}/sections/{section['id']}", json={"label": section["label"] + " "}
    )
    reverted = client.patch(
        f"{BASE}/sections/{section['id']}", json={"label": section["label"]}
    )
    check(
        "13  edit section",
        section_edit.status_code == 200 and reverted.status_code == 200,
        section_edit.text[:200],
    )

    # ----------------------------------------------------------------- 14
    stage_edit = client.patch(f"{BASE}/stages/2", json={"name": "POC / Pilot (edited)"})
    stage_back = client.patch(f"{BASE}/stages/2", json={"name": "POC / Pilot"})
    check(
        "14  edit stage",
        stage_edit.status_code == 200
        and stage_edit.json()["name"] == "POC / Pilot (edited)"
        and stage_back.status_code == 200,
        stage_edit.text[:200],
    )

    # ----------------------------------------------------------------- 16
    published = client.post(f"{BASE}/publish", json={"note": "Round 6 test — regeneration"})
    # Four files, not three: Round-6 gap closure made module_split.json's
    # structural blocks (ranges, pipeline, stage_field, reassign) generated from
    # PostgreSQL too, so a publish regenerates it alongside the other three. Its
    # hand-authored blocks are preserved — see metadata_spec.module_split_document.
    check(
        "16  publish regenerates the JSON",
        published.status_code == 200
        and sorted(published.json()["written"])
        == sorted(
            [
                f"frontend\\spec\\{FIELDS_JSON}",
                f"frontend\\spec\\{PICKLISTS_JSON}",
                f"frontend\\spec\\{STAGES_JSON}",
                "frontend\\spec\\module_split.json",
            ]
        ),
        str(published.json().get("written")),
    )

    # ----------------------------------------------------------------- 17
    # The frontend reads what was written: the field created in check 1 is in
    # the file the application imports, and it got there without anyone
    # editing that file by hand.
    check(
        "17  frontend spec contains the change",
        "leads.r6_test_field" in api_names_in_spec(),
        "r6_test_field missing from fields.json",
    )

    # ----------------------------------------------------------------- 18
    # A BAD DRAFT MUST NOT PUBLISH. Point the test field at a picklist, then
    # deactivate that picklist: a picklist field with no options behind it is
    # an unanswerable dropdown, and publish has to refuse it.
    client.patch(
        f"{BASE}/fields/{new_definition_id}",
        json={"field_type": "picklist", "picklist_key": "r6_test_picklist"},
    )
    client.patch(f"{BASE}/picklists/r6_test_picklist", json={"active": False})

    hashes_before_bad = spec_hashes()
    bad = client.post(f"{BASE}/publish", json={"note": "Round 6 test — should be refused"})
    versions_after = client.get(f"{BASE}/versions").json()
    check(
        "18  bad draft does not become published",
        bad.status_code == 422
        and spec_hashes() == hashes_before_bad
        and not any("should be refused" in (v["note"] or "") for v in versions_after),
        f"status={bad.status_code}",
    )

    # Put the draft back in a publishable state.
    client.patch(f"{BASE}/picklists/r6_test_picklist", json={"active": True})
    client.patch(
        f"{BASE}/fields/{new_definition_id}", json={"field_type": "text", "picklist_key": None}
    )

    # ----------------------------------------------------------------- 19
    # Published versions are immutable: the API offers no way to change one.
    version_routes = [
        route
        for route, methods in (
            (path, set(spec))
            for path, spec in app.openapi()["paths"].items()
        )
        if route.startswith(f"{BASE}/versions/") and methods & {"put", "patch", "delete"}
    ]
    detail = client.get(f"{BASE}/versions/{baseline_version}").json()
    again = client.get(f"{BASE}/versions/{baseline_version}").json()
    check(
        "19  published versions are immutable",
        not version_routes and detail["snapshot"] == again["snapshot"],
        f"mutating routes: {version_routes}",
    )

    # ----------------------------------------------------------------- 20
    # Roll back to the baseline. The test field was created after it, so it
    # must go — logically, and it must still be restorable afterwards.
    rolled = client.post(
        f"{BASE}/versions/{baseline_version}/rollback",
        json={"note": "Round 6 test — rollback"},
    )
    rolled_back_ok = (
        rolled.status_code == 200
        and rolled.json()["version"]["restored_from"] == baseline_version
        and "leads.r6_test_field" not in api_names_in_spec()
    )
    deleted_after = client.get(
        f"{BASE}/fields", params={"module": "leads", "status": "deleted"}
    ).json()
    survived = any(f["id"] == new_field_id for f in deleted_after)
    check(
        "20  rollback republishes an earlier snapshot",
        rolled_back_ok and survived,
        f"status={rolled.status_code} survived_logically={survived}",
    )

    # ------------------------------------------------------------ teardown
    # Every metadata row this test created stays deleted/deactivated rather
    # than being dropped — the same rule the feature itself follows — except
    # the picklist, which nothing references and which would otherwise leave a
    # permanent r6_test_picklist in the register.
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM picklist_values WHERE picklist_key = 'r6_test_picklist'")
        )
        db.execute(text("DELETE FROM picklists WHERE picklist_key = 'r6_test_picklist'"))
        db.execute(
            text("DELETE FROM field_placements WHERE api_name = 'r6_test_field'")
        )
        db.execute(
            text("DELETE FROM field_definitions WHERE api_name = 'r6_test_field'")
        )
        db.execute(
            text("DELETE FROM opportunities WHERE opportunity_id = :id"),
            {"id": opportunity_id},
        )
        db.commit()

    final = client.post(f"{BASE}/publish", json={"note": "Round 6 test — teardown"})
    check(
        "21  spec files are byte-identical to how the test found them",
        final.status_code == 200 and spec_hashes() == before,
        str({k: (before[k], spec_hashes()[k]) for k in before if before[k] != spec_hashes()[k]}),
    )

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for line in failed:
        print(f"  ! {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

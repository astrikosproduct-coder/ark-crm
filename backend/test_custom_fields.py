"""
End-to-end test of dynamic Administration-field values in custom_fields JSONB.

Run:  python test_custom_fields.py

Tests A to I of the dynamic-field brief, against the real database through the
real API. The assertions that matter are made against PostgreSQL directly —
`SELECT custom_fields FROM leads`, `information_schema.columns` — rather than
against the API's own account of itself, because what is being proved is where
the bytes actually went.

The claim under test, end to end:

    Admin creates a field  ->  field_metadata, storage='custom_fields'
    User enters a value    ->  leads.custom_fields->>'rfp_document_file'
    No ALTER TABLE, ever.

Everything it creates is removed in the teardown, including its own Lead and its
own admin fields; register metadata is left exactly as found.
"""

import sys

from sqlalchemy import text

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

# This test writes. Refuse to run against the database the prototype is
# demonstrated from — the copy is made by run_tests.py. See test_db.py.
require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

META = "/api/admin/metadata"
client = TestClient(app)

# Every route is mounted behind require_access / require_admin, which read a
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


def sql(statement: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(statement), params).fetchall()


def column_exists(table: str, column: str) -> bool:
    return bool(
        sql(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c",
            t=table,
            c=column,
        )
    )


def stored_custom_fields(lead_id: str) -> dict:
    rows = sql("SELECT custom_fields FROM leads WHERE lead_id = :id", id=lead_id)
    return rows[0][0] if rows else {}


def create_admin_field(section_id: int, api_name: str, label: str, field_type: str):
    return client.post(
        f"{META}/fields",
        json={
            "module_key": "leads",
            "section_id": section_id,
            "api_name": api_name,
            "label": label,
            "field_type": field_type,
            "requirement": "Optional",
            "description": "Created by test_custom_fields.py",
        },
    )


def main() -> int:
    print("Dynamic admin fields — custom_fields JSONB\n")

    lead_id = "LEAD-CFTEST"
    created_field_ids: list[int] = []

    # Snapshot of an existing account, for Test I.
    account_before = sql(
        "SELECT account_id, account_name, region, segment FROM accounts ORDER BY account_id LIMIT 1"
    )

    with SessionLocal() as db:
        db.execute(text("DELETE FROM leads WHERE lead_id = :id"), {"id": lead_id})
        # Round 7: these fields live in field_definitions/field_placements now,
        # not field_metadata (frozen, archival — see migration 0008). Placements
        # first: the FK from field_placements to field_definitions is
        # ON DELETE RESTRICT.
        db.execute(
            text("DELETE FROM field_placements WHERE api_name IN "
                 "('rfp_document_cf','customer_priority_cf')")
        )
        db.execute(
            text("DELETE FROM field_definitions WHERE api_name IN "
                 "('rfp_document_cf','customer_priority_cf')")
        )
        db.commit()

    section = client.get(f"{META}/sections", params={"module": "leads"}).json()[0]

    # ---------------------------------------------------------------- A
    created = create_admin_field(section["id"], "rfp_document_cf", "RFP Document", "file")
    # POST /fields returns a PLACEMENT (FieldOut: `id` is the placement,
    # `definition_id` the canonical field). DELETE/restore act on the
    # DEFINITION, so that id is what teardown and tests E/F need.
    field_id = created.json()["definition_id"] if created.status_code == 201 else None
    if field_id:
        created_field_ids.append(field_id)

    in_metadata = sql(
        "SELECT storage, status FROM field_placements WHERE api_name = 'rfp_document_cf'"
    )
    check(
        "A   admin field is defined in field_placements with storage='custom_fields'",
        created.status_code == 201
        and in_metadata
        and in_metadata[0][0] == "custom_fields"
        and in_metadata[0][1] == "active",
        f"{created.status_code} {in_metadata}",
    )
    check(
        "A   NO physical column was created for it",
        not column_exists("leads", "rfp_document_cf")
        and not column_exists("opportunities", "rfp_document_cf"),
        "a column appeared — ALTER TABLE must never run",
    )
    check(
        "A   leads.custom_fields exists and is JSONB NOT NULL",
        bool(
            sql(
                "SELECT 1 FROM information_schema.columns WHERE table_name='leads' "
                "AND column_name='custom_fields' AND data_type='jsonb' AND is_nullable='NO'"
            )
        ),
        "missing or wrong type",
    )

    # ---------------------------------------------------------------- B
    # Sent FLAT, the way the prototype's form engine actually posts
    # (useRecordForm's toPayload returns one flat object).
    made = client.post(
        "/api/leads",
        json={
            "lead_id": lead_id,
            "opportunity_name": "Custom field test",
            "rfp_document_cf": "ABC.pdf",
        },
    )
    stored = stored_custom_fields(lead_id)
    check(
        "B   value is stored in leads.custom_fields in PostgreSQL",
        made.status_code == 201 and stored.get("rfp_document_cf") == "ABC.pdf",
        f"status={made.status_code} custom_fields={stored}",
    )

    # ---------------------------------------------------------------- C
    read = client.get(f"/api/leads/{lead_id}")
    check(
        "C   value reads back through the API, flat like a register field",
        read.status_code == 200 and read.json().get("rfp_document_cf") == "ABC.pdf",
        f"status={read.status_code} body_key={read.json().get('rfp_document_cf')!r}",
    )

    # ---------------------------------------------------------------- D
    second = create_admin_field(
        section["id"], "customer_priority_cf", "Customer Priority", "text"
    )
    if second.status_code == 201:
        created_field_ids.append(second.json()["id"])

    # This one uses the EXPLICIT object form rather than a flat key.
    client.patch(
        f"/api/leads/{lead_id}",
        json={"custom_fields": {"customer_priority_cf": "High"}},
    )
    stored = stored_custom_fields(lead_id)
    typed = sql(
        "SELECT opportunity_name FROM leads WHERE lead_id = :id", id=lead_id
    )
    check(
        "D   several admin fields coexist in one JSONB, typed columns untouched",
        stored.get("rfp_document_cf") == "ABC.pdf"
        and stored.get("customer_priority_cf") == "High"
        and typed[0][0] == "Custom field test",
        f"custom_fields={stored} opportunity_name={typed}",
    )

    # ---------------------------------------------------------------- G
    # A REGISTER field must keep using its typed column and must never be
    # copied into the JSONB.
    client.patch(f"/api/leads/{lead_id}", json={"country": "United Arab Emirates"})
    typed = sql("SELECT country, custom_fields FROM leads WHERE lead_id = :id", id=lead_id)
    check(
        "G   register field wrote to its typed column, NOT to custom_fields",
        typed[0][0] == "United Arab Emirates" and "country" not in (typed[0][1] or {}),
        f"country={typed[0][0]!r} custom_fields={typed[0][1]}",
    )

    # ---------------------------------------------------------------- H
    # Flat unknown key: ignored, exactly as before this feature existed —
    # that same flat payload also carries id, __labels and computed values.
    client.patch(f"/api/leads/{lead_id}", json={"not_a_field_at_all": "junk"})
    stored = stored_custom_fields(lead_id)
    flat_ignored = "not_a_field_at_all" not in stored

    # Explicit object: the caller asserted these ARE admin fields, so an
    # unknown one is an error rather than something to quietly drop.
    rejected = client.patch(
        f"/api/leads/{lead_id}",
        json={"custom_fields": {"not_a_field_at_all": "junk"}},
    )
    stored_after = stored_custom_fields(lead_id)
    check(
        "H   unknown field is never stored as a custom field",
        flat_ignored
        and rejected.status_code == 422
        and "not_a_field_at_all" not in stored_after,
        f"flat_ignored={flat_ignored} explicit_status={rejected.status_code} stored={stored_after}",
    )

    # A typo of a REAL field is caught the same way — the case that would
    # otherwise become a permanent orphan key nobody sees again.
    typo = client.patch(
        f"/api/leads/{lead_id}", json={"custom_fields": {"rfp_documnet_cf": "X"}}
    )
    check(
        "H   a typo of a real admin field is rejected, not stored",
        typo.status_code == 422
        and "rfp_documnet_cf" not in stored_custom_fields(lead_id),
        f"status={typo.status_code}",
    )

    # ---------------------------------------------------------------- E
    deleted = client.request("DELETE", f"{META}/fields/{field_id}", json={})
    client.post(f"{META}/publish", json={"note": "custom-fields test — delete"})

    # Round 7: field_metadata is frozen; status now lives on field_definitions.
    state = sql(
        "SELECT status FROM field_definitions WHERE api_name = 'rfp_document_cf'"
    )
    stored = stored_custom_fields(lead_id)
    import json as _json

    published = _json.loads(
        (__import__("pathlib").Path(__file__).resolve().parent.parent
         / "frontend" / "spec" / "fields.json").read_text(encoding="utf-8")
    )
    gone_from_ui = not any(r["api_name"] == "rfp_document_cf" for r in published)

    check(
        "E   deleting the field is logical only — the JSONB value survives",
        deleted.status_code == 200
        and state[0][0] == "deleted"
        and gone_from_ui
        and stored.get("rfp_document_cf") == "ABC.pdf",
        f"status={state} gone_from_ui={gone_from_ui} custom_fields={stored}",
    )
    check(
        "E   no column was dropped, and custom_fields is still there",
        column_exists("leads", "custom_fields"),
        "custom_fields disappeared",
    )

    # ---------------------------------------------------------------- F
    restored = client.post(f"{META}/fields/{field_id}/restore")
    client.post(f"{META}/publish", json={"note": "custom-fields test — restore"})

    read = client.get(f"/api/leads/{lead_id}")
    published = _json.loads(
        (__import__("pathlib").Path(__file__).resolve().parent.parent
         / "frontend" / "spec" / "fields.json").read_text(encoding="utf-8")
    )
    back_in_ui = any(r["api_name"] == "rfp_document_cf" for r in published)

    check(
        "F   restoring the field shows the original value again",
        restored.status_code == 200
        and back_in_ui
        and read.json().get("rfp_document_cf") == "ABC.pdf",
        f"back_in_ui={back_in_ui} value={read.json().get('rfp_document_cf')!r}",
    )

    # ---------------------------------------------------------------- I
    account_after = sql(
        "SELECT account_id, account_name, region, segment FROM accounts ORDER BY account_id LIMIT 1"
    )
    empties = sql(
        "SELECT count(*) FROM accounts WHERE custom_fields IS NULL"
    )
    check(
        "I   existing records are unchanged and defaulted to '{}'",
        account_before == account_after and empties[0][0] == 0,
        f"before={account_before} after={account_after} nulls={empties[0][0]}",
    )

    # ------------------------------------------------------------ teardown
    with SessionLocal() as db:
        db.execute(text("DELETE FROM leads WHERE lead_id = :id"), {"id": lead_id})
        db.execute(
            text("DELETE FROM field_placements WHERE api_name IN "
                 "('rfp_document_cf','customer_priority_cf')")
        )
        db.execute(
            text("DELETE FROM field_definitions WHERE api_name IN "
                 "('rfp_document_cf','customer_priority_cf')")
        )
        db.execute(
            text("DELETE FROM metadata_versions WHERE note LIKE 'custom-fields test%'")
        )
        db.commit()

    client.post(f"{META}/publish", json={"note": "custom-fields test — teardown"})
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM metadata_versions WHERE note LIKE 'custom-fields test%'")
        )
        db.commit()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for line in failed:
        print(f"  ! {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

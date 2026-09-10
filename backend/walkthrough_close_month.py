"""
Walkthrough — Expected Close Month as record state, end to end.

    python walkthrough_close_month.py

Proves the four things the change claims, against the real API and the real
database, and cleans up after itself:

  1. it is on all three pipeline modules, in RECORD STATE, at every stage;
  2. a per-stage value persists — `expected_close_month__s<stage>` survives a
     round trip, which is what makes a revision history exist at all;
  3. the base column still holds the current answer on each module, so the
     list column and the header chip keep reading one date;
  4. Close Date Pushback Count is gone from the register and from the payload,
     and no business column was dropped to do it.

Point 2 is the one worth running. Before this change the field was a single
column on `leads` and a revision overwrote its predecessor, which is exactly
why close_date_pushback_count could never count anything.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.metadata_resolver import resolved_fields  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
sign_in_as_admin(app)

RECORD_STATE = "RECORD STATE — each module keeps its own instance"
FIELD = "expected_close_month"
GONE = "close_date_pushback_count"

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


def main() -> int:
    print("Expected Close Month — record state on all three pipeline modules\n")

    # ---------------------------------------------------------- 1. placement
    print("1  where the field is")
    with SessionLocal() as db:
        for module in ("leads", "opportunities", "deals"):
            rows = {f["api_name"]: f for f in resolved_fields(db, module)}
            row = rows.get(FIELD)
            check(
                f"{module}: {FIELD} is placed",
                row is not None,
                "no placement",
            )
            if row is None:
                continue
            check(
                f"{module}: in RECORD STATE",
                row["section"] == RECORD_STATE,
                f"section={row['section']!r}",
            )
            check(
                f"{module}: still Mandatory from stage 0",
                row["requirement"] == "Mandatory" and row["mandatory_from"] == 0,
                f"requirement={row['requirement']!r} mandatory_from={row['mandatory_from']}",
            )
            check(f"{module}: {GONE} is gone", GONE not in rows, "still present")

    # Leads' own placement is the one that must be askable at every stage; the
    # other two carry capture_stage 0, which is outside their range and so is
    # never claimed by a stage tab. See close_month_record_state.py.
    with SessionLocal() as db:
        leads = {f["api_name"]: f for f in resolved_fields(db, "leads")}
        row = leads[FIELD]
        check(
            "leads: capture_any_stage, no capture_stage",
            row["capture_stage"] is None and row["capture_any_stage"] is True,
            f"capture_stage={row['capture_stage']} any={row['capture_any_stage']}",
        )

    # ------------------------------------------------------- 2. the history
    print("\n2  a per-stage value persists")
    lead_id = "LEAD-CMTEST"
    sql_delete = "DELETE FROM leads WHERE lead_id = :id"
    with engine.begin() as connection:
        connection.execute(text(sql_delete), {"id": lead_id})

    made = client.post(
        "/api/leads",
        json={
            "lead_id": lead_id,
            "opportunity_name": "Close-month walkthrough",
            "project_stage": "0 Connect",
            "expected_close_month": "2026-11-01",
            "expected_close_month__s0": "2026-11-01",
        },
    )
    check("lead created", made.status_code in (200, 201), f"{made.status_code} {made.text[:120]}")

    # Stage 3 revises it. The Stage 0 answer must survive that.
    revised = client.patch(
        f"/api/leads/{lead_id}",
        json={
            "expected_close_month": "2027-02-01",
            "expected_close_month__s3": "2027-02-01",
        },
    )
    check("stage 3 revision accepted", revised.status_code == 200, str(revised.status_code))

    read = client.get(f"/api/leads/{lead_id}")
    body = read.json() if read.status_code == 200 else {}
    check(
        "stage 0's answer survived the stage 3 revision",
        body.get("expected_close_month__s0") == "2026-11-01",
        f"got {body.get('expected_close_month__s0')!r}",
    )
    check(
        "stage 3's answer is stored under its own key",
        body.get("expected_close_month__s3") == "2027-02-01",
        f"got {body.get('expected_close_month__s3')!r}",
    )
    check(
        "the base column holds the current answer",
        str(body.get("expected_close_month")) == "2027-02-01",
        f"got {body.get('expected_close_month')!r}",
    )
    check(
        "two stages recorded — the history a pushback count needs",
        len([k for k in body if k.startswith(f"{FIELD}__s")]) == 2,
        str([k for k in body if k.startswith(f"{FIELD}__s")]),
    )
    check(f"{GONE} is not in the payload", GONE not in body, "still served")

    # ------------------------------------- 3. the base column on each module
    print("\n3  the base column exists where the field is now placed")
    for table in ("leads", "opportunities", "deals"):
        exists = bool(
            sql(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c",
                t=table,
                c=FIELD,
            )
        )
        check(f"{table}.{FIELD} column exists", exists, "missing")

    # ----------------------------------------------- 4. nothing was dropped
    print("\n4  the delete was logical")
    definition = sql(
        "SELECT status FROM field_definitions WHERE api_name = :n", n=GONE
    )
    check(
        f"{GONE} definition row still exists, status 'deleted'",
        bool(definition) and definition[0][0] == "deleted",
        str(definition),
    )
    placements = sql(
        "SELECT module_key, status, deleted_by_cascade FROM field_placements "
        "WHERE api_name = :n ORDER BY module_key",
        n=GONE,
    )
    check(
        "all three placements deleted, stamped as a cascade so restore works",
        len(placements) == 3
        and all(status == "deleted" and cascade for _m, status, cascade in placements),
        str(placements),
    )

    with engine.begin() as connection:
        connection.execute(text(sql_delete), {"id": lead_id})
    print(f"\n  cleaned up {lead_id}")

    print()
    print("=" * 74)
    if failed:
        print(f"{len(passed)} passed, {len(failed)} FAILED\n")
        for line in failed:
            print(f"    {line}")
        return 1
    print(f"ALL {len(passed)} CHECKS PASSED")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())

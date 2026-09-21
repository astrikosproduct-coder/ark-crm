"""
Feedback: anyone with a role can send it; only DEVELOPER can read or triage it.

    python run_tests.py test_feedback.py

UX roadmap item 2, 17 Sep 2026 — app/routers/feedback.py, migration 0032.
Checked over HTTP as three real users: a Viewer, an Admin without Developer, and
a Developer without Admin — because "only developers" is a server rule, and a
test that only ever signs in as the all-roles admin could not see it break.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app.auth import current_user  # noqa: E402
from app.clock import now_utc  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Feedback, Role, User, UserRole  # noqa: E402

client = TestClient(app)
failures: list[str] = []

PEOPLE = {
    "viewer": ("USR-T-FB1", "Feedback Viewer", ["VIEWER"]),
    "admin": ("USR-T-FB2", "Feedback Admin", ["ADMIN"]),
    "developer": ("USR-T-FB3", "Feedback Developer", ["DEVELOPER"]),
}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def act_as(key: str) -> None:
    user_id = PEOPLE[key][0]

    def _current_user():
        with SessionLocal() as db:
            user = db.get(User, user_id)
            db.expunge(user)
            return user

    app.dependency_overrides[current_user] = _current_user


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


with SessionLocal() as db:
    check("the DEVELOPER role exists", db.get(Role, "DEVELOPER") is not None)
    for user_id, name, roles in PEOPLE.values():
        if db.get(User, user_id) is None:
            stamp = now_utc()
            db.add(User(user_id=user_id, name=name, email=f"{user_id.lower()}@example.test", active=True, created_at=stamp, updated_at=stamp))
            db.flush()
        for role_id in roles:
            if db.get(UserRole, (user_id, role_id)) is None:
                db.add(UserRole(user_id=user_id, role_id=role_id))
    db.commit()

created: list[str] = []
try:
    print("=" * 74)
    print("  FEEDBACK — anyone sends, developers read")
    print("=" * 74)

    print("\n1  Sending")
    act_as("viewer")
    r = client.post(
        "/api/feedback",
        json={"category": "CONFUSING", "message": "  The stage dialog lost me.  ", "page_path": "/leads/LEAD-00001", "record_ref": "LEAD-00001", "created_by": "USR-T-FB3"},
    )
    check("a Viewer can send feedback", r.status_code == 201, r.text[:300])
    body = r.json() if r.status_code == 201 else {}
    created.append(body.get("id", ""))
    check("…stamped with who sent it, never the body's created_by", body.get("created_by") == "USR-T-FB1", str(body.get("created_by")))
    check("…with the message trimmed", body.get("message") == "The stage dialog lost me.", repr(body.get("message")))
    check("…as New, with the page it came from", body.get("status") == "NEW" and body.get("page_path") == "/leads/LEAD-00001")

    r = client.post("/api/feedback", json={"category": "CONFUSING", "message": "   "})
    check("a blank message is refused in words", r.status_code == 422 and code_of(r) == "FEEDBACK_EMPTY", r.text[:200])
    r = client.post("/api/feedback", json={"category": "NOT_A_CATEGORY", "message": "x"})
    check("an unknown category is refused", r.status_code == 422 and code_of(r) == "FEEDBACK_CATEGORY_UNKNOWN", r.text[:200])

    print("\n2  Reading is DEVELOPER only — enforced on the server")
    check("a Viewer gets 403 reading it", client.get("/api/feedback").status_code == 403)
    act_as("admin")
    check("an Admin without Developer gets 403 too", client.get("/api/feedback").status_code == 403)
    r = client.patch(f"/api/feedback/{created[0]}", json={"status": "READ"})
    check("…and cannot triage it", r.status_code == 403, str(r.status_code))

    act_as("developer")
    r = client.get("/api/feedback", params={"status": "NEW"})
    ids = [x["id"] for x in r.json()] if r.status_code == 200 else []
    check("a Developer reads it", r.status_code == 200 and created[0] in ids, r.text[:200])
    row = next((x for x in r.json() if x["id"] == created[0]), {}) if r.status_code == 200 else {}
    check("…with the sender's name", row.get("created_by_name") == "Feedback Viewer", str(row.get("created_by_name")))
    check("…and the New count on X-New-Count", int(r.headers.get("x-new-count", "0")) >= 1, str(r.headers.get("x-new-count")))

    print("\n3  Triage")
    r = client.patch(f"/api/feedback/{created[0]}", json={"status": "READ"})
    check("marking it Read stamps who read it", r.status_code == 200 and r.json()["read_by"] == "USR-T-FB3" and r.json()["read_at"], r.text[:200])
    r = client.patch(f"/api/feedback/{created[0]}", json={"status": "DONE"})
    check("Done keeps the first reader", r.status_code == 200 and r.json()["read_by"] == "USR-T-FB3")
    r = client.patch(f"/api/feedback/{created[0]}", json={"status": "NEW"})
    check("back to New clears it", r.status_code == 200 and r.json()["read_by"] is None)
    r = client.patch(f"/api/feedback/{created[0]}", json={"status": "ARCHIVED"})
    check("an unknown status is refused", r.status_code == 422 and code_of(r) == "FEEDBACK_STATUS_UNKNOWN", r.text[:200])
    r = client.patch("/api/feedback/FB-99999", json={"status": "READ"})
    check("a missing item is a plain 404", r.status_code == 404 and code_of(r) == "NOT_FOUND")

finally:
    app.dependency_overrides.pop(current_user, None)
    with SessionLocal() as db:
        db.execute(delete(Feedback).where(Feedback.created_by.in_([p[0] for p in PEOPLE.values()])))
        db.execute(delete(UserRole).where(UserRole.user_id.in_([p[0] for p in PEOPLE.values()])))
        db.execute(delete(User).where(User.user_id.in_([p[0] for p in PEOPLE.values()])))
        db.commit()
        leftover = db.scalars(select(User.user_id).where(User.user_id.like("USR-T-FB%"))).all()
    print("\nCleanup", "done" if not leftover else f"left {leftover}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")

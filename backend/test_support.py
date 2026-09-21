"""
Shared scaffolding for the backend test scripts: a signed-in client, and a
guard that puts the field register back however a test leaves it.

    from test_support import sign_in_as_admin, RegisterGuard

    client = TestClient(app)
    sign_in_as_admin(app)

    with RegisterGuard() as guard:
        ...                      # a test that writes placements
    guard.report()               # says what it had to repair, if anything

WHY THE AUTH OVERRIDE EXISTS
-----------------------------
Every route is mounted behind `require_access` or `require_administration`
(app/main.py), both of which resolve through `current_user`, which reads a
signed-in user id out of the session cookie. A TestClient has no cookie and
no way to get one: sign-in goes through Microsoft Entra, and there is no
password to post. So every HTTP-based test returned 401 and asserted nothing
— test_placements.py alone reported 13 failures, all of them "Not signed in."

The fix overrides `current_user` and nothing else. FastAPI resolves overrides
through the whole sub-dependency graph, so `require_access` and
`require_administration` still run their own checks (roles present, DEVELOPER
among them, account active) against the user this hands them. That matters:
overriding `require_administration` directly would have stubbed out the authorisation rules as
well as the authentication, and a test suite that cannot fail on a permission
bug is worse than one that cannot run.

The user is a REAL row, read from the database, not a fabricated object. A
synthetic User would drift from the schema the moment `users` grows a column,
and `created_by` stamps written during a test would name a user that does not
exist.

WHY THE REGISTER GUARD EXISTS
------------------------------
A test that writes placements is one bug away from leaving the register
damaged, and that is not hypothetical: the Phase A1 anchor fixture reset the
placements it touched to NULL on teardown, which after A2 unanchored On Hold
Reason and Closed Lost Reason Code on Leads. The screens went back to the
two-save journey and nothing said so.

That happened because the scripts ran against the live development database —
the same one the prototype is demonstrated from. They no longer do: run_tests.py
copies it and points DATABASE_URL at the copy, and every writing test calls
test_db.require_test_database() and refuses otherwise. This docstring used to
argue that a second database was a bigger change than it looked, because
bootstrap_metadata.py, seed.py and the migrate_* scripts all assume one, and a
second built from scratch would have to be kept in step. CREATE DATABASE ...
TEMPLATE sidesteps that entirely — see test_db.py.

So this class is no longer the thing standing between a test and a damaged
demo. It is still worth having, and its job is now the narrower one: a test
that writes the register and does not put it back is a broken test, and
`repairs` is how you find out rather than carrying the mess into the next
test in the same run.

RegisterGuard snapshots every mutable configuration column of every placement
on entry and restores any that differ on exit — including after an exception,
which is when a test is most likely to have skipped its own cleanup. It does
NOT touch business tables; a test that creates an Opportunity is still
responsible for deleting it.

WHAT IT DELIBERATELY DOES NOT DO
---------------------------------
It does not roll back in a transaction. The tests exercise the real API over
HTTP, and those requests open and commit their own sessions; a transaction
held open here would deadlock against them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldPlacement

# Every placement column an Administration edit can change. Identity columns
# (id, definition_id, module_key, api_name) are deliberately absent: if one of
# those moved, the row is not the same row and restoring it would be a guess.
GUARDED_COLUMNS = (
    "section_id",
    "sort_order",
    "label_override",
    "capture_stage",
    "capture_any_stage",
    "mandatory_from",
    "blocks_transition",
    "requirement",
    "required_on_skip",
    "visibility_condition",
    "condition",
    "value_mode",
    "value_locked",
    "editable",
    "storage",
    "anchor_field",
    "anchor_position",
    "layout_span",
    # 'active' is not a column here — a placement carries `status`
    # ('active' | 'deleted') plus its deletion stamps, because an
    # Administration delete is a deliberate act that has to be told apart from
    # a field merely switched off. See FieldMetadata's docstring in models.py.
    "status",
    "deleted_at",
    "deleted_by",
    "deleted_by_cascade",
)


def admin_user():
    """
    The real signed-in user the tests act as: active, and holding DEVELOPER —
    the role that opens Administration in V1 (it was ADMIN until 21 Sep 2026).

    Read fresh from the database rather than cached, so a suite that
    deactivates a user and expects a 403 gets one.
    """
    from app.auth import DEVELOPER_ROLE
    from app.models import User

    with SessionLocal() as db:
        candidates = db.scalars(select(User).where(User.active.is_(True))).all()
        for user in candidates:
            if any(role.role_id == DEVELOPER_ROLE for role in user.roles):
                # Detached from this session on purpose: the override hands it
                # to a request that has a session of its own.
                db.expunge(user)
                return user

    raise RuntimeError(
        "No active user holding DEVELOPER. Administration tests cannot run without "
        "one — check `users` and `user_roles`, or run seed.py."
    )


def sign_in_as_admin(app) -> Any:
    """
    Make every request from a TestClient of `app` act as the admin user.

    Returns the user, so a test can assert against the identity its own writes
    were stamped with.
    """
    from app.auth import current_user

    user = admin_user()

    def _current_user():
        # Re-attached per request by the route's own session when it touches
        # relationships; the identity map keys on the primary key, so handing
        # back the same detached instance is safe.
        with SessionLocal() as db:
            return db.merge(user, load=True)

    app.dependency_overrides[current_user] = _current_user
    return user


def sign_out(app) -> None:
    """Drop the override — for a test that wants to assert a real 401."""
    from app.auth import current_user

    app.dependency_overrides.pop(current_user, None)


class RegisterGuard:
    """
    Restores every field placement's configuration to how it was on entry.

    Use as a context manager. `repairs` lists what had to be put back, which a
    test should print: a non-empty list means the test under it did not clean
    up after itself, and that is worth seeing rather than silently fixing.
    """

    def __init__(self, remove_new: bool = True) -> None:
        self.before: dict[int, dict[str, Any]] = {}
        self.definitions_before: set[int] = set()
        self.repairs: list[str] = []
        # Rows CREATED inside the window are removed on exit as well as rows
        # changed. That is not over-reach: a test that adds a field to the
        # register and leaves it there has changed the configuration the
        # prototype demonstrates. test_round6_gaps.py did exactly this — its
        # teardown deleted from the legacy field_metadata table and so removed
        # nothing, and ten r6g_* fields reached spec/fields.json on publish.
        # Pass remove_new=False for a test whose whole subject is that a
        # created field survives something.
        self.remove_new = remove_new

    def _snapshot(self) -> dict[int, dict[str, Any]]:
        with SessionLocal() as db:
            return {
                row.id: {col: getattr(row, col) for col in GUARDED_COLUMNS}
                for row in db.scalars(select(FieldPlacement))
            }

    def _definition_ids(self) -> set[int]:
        from app.models import FieldDefinition

        with SessionLocal() as db:
            return set(db.scalars(select(FieldDefinition.id)))

    def __enter__(self) -> RegisterGuard:
        self.before = self._snapshot()
        self.definitions_before = self._definition_ids()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Runs on the exception path too — that is the case worth covering, a
        # test that raised before reaching its own teardown.
        self.restore()
        return False

    def restore(self) -> list[str]:
        after = self._snapshot()
        with SessionLocal() as db:
            for placement_id, original in self.before.items():
                current = after.get(placement_id)
                if current is None:
                    self.repairs.append(
                        f"placement {placement_id} no longer exists — NOT restored, "
                        f"a deleted row cannot be rebuilt from a column snapshot"
                    )
                    continue
                changed = {c: v for c, v in original.items() if current[c] != v}
                if not changed:
                    continue
                row = db.get(FieldPlacement, placement_id)
                if row is None:
                    continue
                for column, value in changed.items():
                    setattr(row, column, value)
                self.repairs.append(
                    f"{row.module_key}.{row.api_name}: "
                    + ", ".join(
                        f"{c} {current[c]!r} -> {v!r}" for c, v in sorted(changed.items())
                    )
                )
            db.commit()

        if self.remove_new:
            self._remove_new()
        return self.repairs

    def _remove_new(self) -> None:
        """
        Drop definitions (and their placements) that did not exist on entry.

        Placements first: field_placements -> field_definitions is ON DELETE
        RESTRICT, so a definition still pointed at refuses to go.
        """
        from app.models import FieldDefinition

        with SessionLocal() as db:
            added = [
                row
                for row in db.scalars(select(FieldDefinition))
                if row.id not in self.definitions_before
            ]
            if not added:
                return
            for definition in added:
                placements = db.scalars(
                    select(FieldPlacement).where(
                        FieldPlacement.definition_id == definition.id
                    )
                ).all()
                for placement in placements:
                    db.delete(placement)
                self.repairs.append(
                    f"removed field {definition.api_name!r} created during the test "
                    f"({len(placements)} placement(s))"
                )
                db.delete(definition)
            db.commit()

    def report(self) -> None:
        if not self.repairs:
            print("  register guard: clean — nothing needed restoring")
            return
        print(f"  register guard: REPAIRED {len(self.repairs)} placement(s)")
        for line in self.repairs:
            print(f"      {line}")

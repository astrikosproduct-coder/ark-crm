"""
Phase 0 of the Entra SSO cutover: replace the demo users with one real admin.

Run:  python reset_users_for_sso.py            # dry run
      python reset_users_for_sso.py --apply

WHY THIS EXISTS
---------------
Every users row today is prototype fixture data on the wrong domain — six
accounts at @astrikos.com, plus a gmail admin and a near-duplicate — while the
real tenant is astrikos.ai. None of them would match a Microsoft sign-in, so on
cutover day the first person in would be auto-provisioned as a brand-new user
with ZERO roles, and no existing account could sign in to grant them anything.
That is a total lockout with no password fallback.

Confirmed with the user: all current data is demo data and needs no preserving.
So rather than correcting six fictional emails, this clears them and seeds
exactly one real row, which is the ONE thing that must be right before sign-in
is switched on:

    kishan.pawar@astrikos.ai  ·  Kishan Pawar  ·  ADMIN

Everyone else signs in when they need to, is auto-provisioned with no roles, and
is granted access from Administration — leaving no fictional accounts behind.

Demo records owned by the removed users (leads, accounts, contacts) have their
owner columns cleared rather than being deleted: every one of those FKs is ON
DELETE SET NULL, so this only makes explicit what the database would do anyway.

Idempotent: re-running leaves the seeded admin exactly as it is.
"""

import sys

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import Role, User, UserRole

ADMIN_EMAIL = "kishan.pawar@astrikos.ai"
ADMIN_NAME = "Kishan Pawar"
ADMIN_USER_ID = "USR-001"
ADMIN_ROLE = "ADMIN"

# Owner columns that point at users. All are ON DELETE SET NULL; cleared
# explicitly so the dry run can report exactly what will change.
OWNER_COLUMNS = [
    ("leads", ("bd_owner", "sales_owner", "presales_owner", "created_by", "modified_by")),
    ("accounts", ("account_owner",)),
    ("contacts", ("engagement_owner", "created_by", "modified_by")),
    ("opportunities", ("created_by", "modified_by", "contract_review_sign_off_by")),
    ("deals", ("created_by", "modified_by", "delivery_pm")),
]


def _existing_columns(db, table: str, columns: tuple) -> list:
    """Only touch columns that actually exist — the schema differs per table."""
    present = {
        row[0]
        for row in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": table},
        )
    }
    return [c for c in columns if c in present]


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        admin_role = db.get(Role, ADMIN_ROLE)
        if admin_role is None:
            print(f"ABORT: role {ADMIN_ROLE} is not seeded. Run seed.py first.")
            return

        users = db.scalars(select(User)).all()
        keep = db.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL.lower()))
        remove = [u for u in users if keep is None or u.user_id != keep.user_id]

        print(f"Seeding admin : {ADMIN_EMAIL} ({ADMIN_NAME}) with role {ADMIN_ROLE}")
        print(f"Removing      : {len(remove)} demo user(s)")
        for u in remove:
            print(f"    - {u.user_id} {u.name} <{u.email}>")

        if not apply:
            print("\nDry run. Re-run with --apply.")
            return

        # 1. Clear owner references so nothing points at a user about to go.
        for table, columns in OWNER_COLUMNS:
            for column in _existing_columns(db, table, columns):
                db.execute(text(f"UPDATE {table} SET {column} = NULL"))

        # 2. Remove the demo users and their role assignments.
        #
        # Through the ORM relationship, not raw SQL: User.roles is loaded
        # eagerly (lazy="selectin"), so deleting the junction rows behind
        # SQLAlchemy's back makes its own cascade find nothing to delete and
        # raise StaleDataError. Clearing the collection lets it issue both
        # deletes itself, in the right order.
        for u in remove:
            u.roles.clear()
        db.flush()
        for u in remove:
            db.delete(u)
        db.flush()

        # 3. Seed (or correct) the one real admin.
        if keep is None:
            keep = User(
                user_id=ADMIN_USER_ID,
                name=ADMIN_NAME,
                email=ADMIN_EMAIL,
                active=True,
            )
            db.add(keep)
            db.flush()
        else:
            keep.name = ADMIN_NAME
            keep.active = True

        # entra_object_id is deliberately left NULL: it is filled on the first
        # real sign-in, which is what LINKS this row to the Microsoft identity.
        # Guessing it here would lock the account to an id nobody can verify.
        keep.roles.clear()
        db.flush()
        db.add(UserRole(user_id=keep.user_id, role_id=ADMIN_ROLE))

        db.commit()
        print(f"\nApplied. {keep.user_id} <{keep.email}> is the only user, holding {ADMIN_ROLE}.")
        print("Their first Microsoft sign-in links this row via the oid claim.")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)

"""
One-time reconciliation: free USR-001..USR-006 for the user directory.

Run:  python reconcile_user_ids.py            # dry run, prints the plan
      python reconcile_user_ids.py --apply    # performs the moves

Why this exists
---------------
Users used to be a mock collection in frontend/spec/seed/users.json. Records
across spec/seed/*.json reference USR-001 to USR-006 forty-two times as
bd_owner, account_owner, engagement_owner and so on. Now that users are a real
database resource, those six ids must belong to the same six people, or every
existing demo record silently repoints to a different owner or blanks out.

The database was seeded earlier with an administrator on USR-001, and a second
account was created on USR-002 while testing. Both sit on ids the directory
needs. This script moves them out of the way to the USR-9xx range rather than
deleting them: nothing is destroyed, and the move is reversible.

A primary-key change needs the foreign key repointed by hand — user_roles has
ON DELETE CASCADE but no ON UPDATE CASCADE, so an in-place UPDATE of user_id is
rejected by PostgreSQL. Each move is therefore copy, repoint, drop, inside one
transaction.

This is a one-off. Once it has run, seed.py maintains the directory and this
file can be deleted.
"""

import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User, UserRole

# (current id, new id, the name we expect to find there — a guard against
# running this against a database that has since moved on).
MOVES = [
    ("USR-001", "USR-900", "ARK Administrator"),
    ("USR-002", "USR-901", "Kishan"),
]


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        planned = []

        for old_id, new_id, expected_name in MOVES:
            user = db.get(User, old_id)

            if user is None:
                print(f"  skip  {old_id} -> {new_id}: no such user (already moved?)")
                continue

            if user.name != expected_name:
                print(
                    f"  SKIP  {old_id} -> {new_id}: expected '{expected_name}' "
                    f"but found '{user.name}'. Not touching it."
                )
                continue

            if db.get(User, new_id) is not None:
                print(f"  SKIP  {old_id} -> {new_id}: {new_id} is already taken.")
                continue

            role_ids = [r.role_id for r in user.roles]
            print(
                f"  move  {old_id} -> {new_id}  '{user.name}' <{user.email}>  "
                f"roles: {', '.join(role_ids) or '(none)'}"
            )
            planned.append((user, new_id, role_ids))

        if not planned:
            print("\nNothing to do.")
            return

        if not apply:
            print(f"\nDry run. {len(planned)} move(s) planned. Re-run with --apply.")
            return

        for user, new_id, role_ids in planned:
            old_id = user.user_id

            # 1. capture the row as plain values BEFORE it is removed
            fields = {
                "name": user.name,
                "email": user.email,
                "active": user.active,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            }

            # 2. drop the old row first. Inserting the copy up front instead
            #    trips the unique index on email — both rows would hold the
            #    same address for the moment between insert and delete.
            #
            #    Deleting the User is enough to clear its user_roles rows:
            #    User.roles is a `secondary` relationship, so the ORM removes
            #    the association rows itself. Bulk-deleting them here as well
            #    makes the two paths race and raises StaleDataError.
            db.delete(user)
            db.flush()

            # 3. re-create it at the new id with its assignments intact
            db.add(User(user_id=new_id, **fields))
            db.flush()
            for role_id in role_ids:
                db.add(UserRole(user_id=new_id, role_id=role_id))
            db.flush()
            print(f"  moved {old_id} -> {new_id}")

        db.commit()
        print(f"\nApplied {len(planned)} move(s).")

        print("\nUsers now:")
        for user in db.scalars(select(User).order_by(User.user_id)):
            roles = ", ".join(r.role_id for r in user.roles) or "(none)"
            print(f"  {user.user_id}  {user.name:20} {roles}")

    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)

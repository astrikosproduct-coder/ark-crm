"""
Idempotent seed for the Administration module.

Run:  python seed.py

Roles are the nine system-defined roles from spec/picklists.json
(administration__roles) — the keys match exactly, so the database and the field
register share one vocabulary. Re-running updates labels in place and never
duplicates a row.
"""

from app.database import Base, SessionLocal, engine
from app.models import Role, User, UserRole

Base.metadata.create_all(bind=engine)

# (role_id, name, description) in workbook sort order.
SYSTEM_ROLES = [
    ("BD_OWNER", "BD Owner", "Owns the pursuit through Stages 0-3."),
    ("SALES_OWNER", "Sales Owner", "Owns the commercial relationship and the close."),
    ("PRESALES_OWNER", "Presales Owner", "Owns demos, POCs and technical evaluation."),
    ("PRODUCT_OWNER", "Product Owner", "Owns solution fit and product commitments."),
    ("DELIVERY_OWNER", "Delivery Owner", "Owns delivery feasibility and Project Success."),
    ("COMMERCIAL_REVIEWER", "Commercial Reviewer", "Reviews margin, discount and red lines."),
    ("APPROVER", "Approver", "Records gate and threshold approval decisions."),
    ("ADMIN", "Admin", "Administers users, roles and configuration."),
    ("VIEWER", "Viewer", "Read-only access."),
    ("DEVELOPER", "Developer", "For development and testing only."),
]

INITIAL_ADMIN = {
    "user_id": "USR-900",
    "name": "ARK Administrator",
    "email": "astrikosproduct@gmail.com",
    "roles": ["ADMIN"],
}

# The user directory, migrated verbatim out of frontend/spec/seed/users.json
# when users stopped being a mock collection and became a database resource.
#
# The ids are NOT arbitrary. Records across spec/seed/*.json reference USR-001
# to USR-006 forty-two times as bd_owner, account_owner, engagement_owner and
# so on. Changing an id here silently repoints or blanks an owner on existing
# demo records, so these are pinned. The initial admin was moved to USR-900 to
# free USR-001, which belongs to Kishan Pawar.
#
# Unlike the roles above, this list is DATA rather than configuration: once a
# person exists, the seed leaves their name, email and roles alone, because an
# admin may legitimately have edited them through the Administration screen.
DIRECTORY_USERS = [
    ("USR-001", "Kishan Pawar", "kishan@astrikos.com",
     ["BD_OWNER", "SALES_OWNER", "PRESALES_OWNER", "COMMERCIAL_REVIEWER", "APPROVER", "ADMIN"]),
    ("USR-002", "Arun Menon", "arun@astrikos.com",
     ["PRODUCT_OWNER", "DELIVERY_OWNER"]),
    ("USR-003", "Priya Raghavan", "priya@astrikos.com",
     ["BD_OWNER"]),
    ("USR-004", "Samir Haque", "samir@astrikos.com",
     ["PRESALES_OWNER"]),
    ("USR-005", "Leena Thomas", "leena@astrikos.com",
     ["COMMERCIAL_REVIEWER"]),
    ("USR-006", "Vikram Shah", "vikram@astrikos.com",
     ["DELIVERY_OWNER"]),
]


def seed() -> None:
    db = SessionLocal()
    try:
        created_roles = 0
        for sort_order, (role_id, name, description) in enumerate(SYSTEM_ROLES, start=1):
            role = db.get(Role, role_id)
            if role is None:
                db.add(
                    Role(
                        role_id=role_id,
                        name=name,
                        description=description,
                        sort_order=sort_order,
                        active=True,
                    )
                )
                created_roles += 1
            else:
                # Keep labels and ordering in step with the spec without
                # touching the assignments that point at this role.
                role.name = name
                role.description = description
                role.sort_order = sort_order

        db.flush()
        print(f"Roles: {created_roles} created, {len(SYSTEM_ROLES) - created_roles} already present")

        created_users = 0
        for user_id, name, email, role_ids in [
            *[(u[0], u[1], u[2], u[3]) for u in DIRECTORY_USERS],
            (
                INITIAL_ADMIN["user_id"],
                INITIAL_ADMIN["name"],
                INITIAL_ADMIN["email"],
                INITIAL_ADMIN["roles"],
            ),
        ]:
            if db.get(User, user_id) is not None:
                # Present already. Left exactly as it is — an admin may have
                # renamed them or changed their roles through the UI, and a
                # seed must never overwrite a deliberate edit.
                continue

            db.add(User(user_id=user_id, name=name, email=email, active=True))
            db.flush()  # user_roles has an FK to this row
            for role_id in role_ids:
                db.add(UserRole(user_id=user_id, role_id=role_id))
            created_users += 1

        total_seeded = len(DIRECTORY_USERS) + 1
        print(
            f"Users: {created_users} created, "
            f"{total_seeded - created_users} already present"
        )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()

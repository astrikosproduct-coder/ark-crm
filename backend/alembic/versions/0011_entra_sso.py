"""Entra SSO: link a users row to its Microsoft directory identity

Revision ID: 0011_entra_sso
Revises: 0010_round3_registration
Create Date: 2026-09-06

Two columns on `users`, and deliberately NO password column — authentication is
Microsoft's job, not this application's.

WHY entra_object_id HOLDS `oid` AND NOT `sub`
---------------------------------------------
Entra issues two identifiers in an ID token, and picking the wrong one is a
lockout waiting to happen:

  * `sub` is a PAIRWISE identifier — the same person gets a DIFFERENT `sub`
    from every app registration. P-1 signs in through a borrowed registration
    (the ARK n8n connector) until the ARK CRM app clears admin consent, so a
    `sub` stored today would stop matching the moment those credentials are
    swapped: every user would return as an unrecognised stranger with zero
    roles, including the only admin.
  * `oid` is the user's object id in the DIRECTORY. It is identical across
    every app registration in the tenant, so swapping registrations is
    invisible to this table.

Nullable because a row may be created by an administrator before its owner has
ever signed in; it is populated on that person's first successful sign-in and
matched on from then on, with email used only for the initial link.
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_entra_sso"
down_revision = "0010_round3_registration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("entra_object_id", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Unique so two rows can never claim the same Microsoft identity. A partial
    # index would do as well; a plain unique index already permits many NULLs in
    # PostgreSQL, which is exactly the "not linked yet" case.
    op.create_unique_constraint("uq_users_entra_object_id", "users", ["entra_object_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_entra_object_id", "users", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "entra_object_id")

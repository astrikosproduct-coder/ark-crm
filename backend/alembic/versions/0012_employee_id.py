"""Employee ID from the Microsoft directory, as an attribute

Revision ID: 0012_employee_id
Revises: 0011_entra_sso
Create Date: 2026-09-06

An ATTRIBUTE, deliberately not an identifier.

The temptation is to show this instead of USR-001, or to key on it outright.
Neither is right:

  * `user_id` stays the primary key. It is referenced by leads.bd_owner,
    sales_owner, presales_owner, created_by/modified_by, accounts.account_owner,
    contacts.engagement_owner, user_roles, audit_log and the transition actor.
    Re-keying all of that onto a field the directory may leave empty would break
    exactly the people whose employeeId was never filled in.
  * `entra_object_id` stays the sign-in link, because it is guaranteed present
    and immutable. employeeId is HR data — it can be edited, and it can be null.

What it IS good for: reconciling CRM users against an HR export, and showing a
number people recognise next to the internal key on the Administration screen.

Nullable and NOT unique: a tenant that does not populate employeeId would
otherwise collide on the second user, turning a cosmetic nicety into a failed
sign-in. Indexed because the reconciliation use case is a lookup by this value.
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_employee_id"
down_revision = "0011_entra_sso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("employee_id", sa.String(length=64), nullable=True))
    op.create_index("ix_users_employee_id", "users", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_users_employee_id", table_name="users")
    op.drop_column("users", "employee_id")

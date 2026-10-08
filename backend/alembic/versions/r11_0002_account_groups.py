"""Accounts: Parent Account, and who was answered "a different company"

Revision ID: r11_0002_account_groups
Revises: r11_0001_location_fields
Create Date: 2026-10-07

Release 1.1, chunk D (decided 6 Oct 2026).

  parent_account         The head of the company's group, one level deep:
                         every member points at the head, the head points at
                         nothing. The API keeps it flat — picking any member
                         files the account under that member's head
                         (app/account_groups.py). ON DELETE SET NULL is the
                         database's fallback only; the API refuses to delete
                         a head that still has companies.
  not_duplicate_of       The accounts the duplicate check's "a different
                         company" answer was given about, so it is not asked
                         again about them — and IS asked about any other
                         (app/account_matching.py). One click, no reason.

DEPLOY ORDER: dump -> alembic upgrade head -> release_1_1_fields_metadata.py
--apply -> release_1_1_location_metadata.py --apply ->
release_1_1_accounts_metadata.py --apply -> start the new code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "r11_0002_account_groups"
down_revision = "r11_0001_location_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "parent_account",
            sa.String(20),
            sa.ForeignKey("accounts.account_id", ondelete="SET NULL", name="fk_accounts_parent_account"),
            nullable=True,
        ),
    )
    op.create_index("ix_accounts_parent_account", "accounts", ["parent_account"])
    op.create_check_constraint("ck_accounts_parent_not_self", "accounts", "parent_account <> account_id")
    op.add_column(
        "accounts",
        sa.Column("not_duplicate_of", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("accounts", "not_duplicate_of")
    op.drop_constraint("ck_accounts_parent_not_self", "accounts", type_="check")
    op.drop_index("ix_accounts_parent_account", table_name="accounts")
    op.drop_constraint("fk_accounts_parent_account", "accounts", type_="foreignkey")
    op.drop_column("accounts", "parent_account")

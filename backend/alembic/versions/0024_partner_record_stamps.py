"""Deal registrations and conflict adjudications record who made them, and when

Revision ID: 0024_partner_stamps
Revises: 0023_field_min_max
Create Date: 2026-09-14

Every other migrated module — leads, opportunities, deals, accounts, contacts —
carries a server-stamped creator and creation instant. These two carried
neither, and their routers wrote nothing to audit_log, so a registration
entered on 14 Sep with a partner Submitted Date of 12 Sep was indistinguishable
from one entered on the 12th. The only way to establish when REG-00003 was
created was to read database backups.

All four columns are NULLABLE, including created_date where leads has NOT NULL.
Rows that already exist have no knowable creation time, and backfilling now()
would stamp them with the day this migration ran — a plausible, wrong date,
which is worse than a blank one. New rows are always stamped by the router.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_partner_stamps"
down_revision = "0023_field_min_max"
branch_labels = None
depends_on = None

TABLES = ("deal_registrations", "registration_conflicts")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "created_by",
                sa.String(20),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(table, sa.Column("created_date", sa.DateTime(timezone=True), nullable=True))
        op.add_column(
            table,
            sa.Column(
                "modified_by",
                sa.String(20),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(table, sa.Column("modified_date", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_created_by", table, ["created_by"])
        op.create_index(f"ix_{table}_modified_by", table, ["modified_by"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_modified_by", table_name=table)
        op.drop_index(f"ix_{table}_created_by", table_name=table)
        op.drop_column(table, "modified_date")
        op.drop_column(table, "modified_by")
        op.drop_column(table, "created_date")
        op.drop_column(table, "created_by")

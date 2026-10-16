"""Per-user list columns and Kanban settings

Revision ID: r11_0003_user_view_preferences
Revises: r11_0002_account_groups
Create Date: 2026-10-14

Release 1.2 (14 Oct 2026): each person arranges their own list columns and
Kanban board, as in Zoho; nobody else's view changes. One row per user and
view; no row is the default view. See models.UserViewPreference.

DEPLOY ORDER: dump -> alembic upgrade head -> release_1_2_partner_tier_metadata.py
--apply -> start the new code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "r11_0003_user_view_preferences"
down_revision = "r11_0002_account_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_view_preferences",
        sa.Column(
            "user_id",
            sa.String(20),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="fk_user_view_preferences_user"),
            primary_key=True,
        ),
        sa.Column("view_key", sa.String(80), primary_key=True),
        sa.Column("settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # page: one module's own page — which view it opens on (Release 1.2).
        sa.CheckConstraint("view_key ~ '^(list|kanban|page):[a-z_]+$'", name="ck_user_view_preferences_key"),
    )


def downgrade() -> None:
    op.drop_table("user_view_preferences")

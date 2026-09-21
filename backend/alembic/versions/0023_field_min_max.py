"""A number field can state its own Min value and Max value

Revision ID: 0023_field_min_max
Revises: 0022_stage_pct
Create Date: 2026-09-14

Scores were typed as plain numbers with the scale written only in prose —
Relationship Score's description says "rated 1 to 10", and nothing held anyone
to it. A threshold is a fact about the VALUE, so it lives on field_definitions
beside max_length: the same concept has the same range on every module.

Both nullable, both inclusive. Null means no bound on that side. Metadata only —
no business table is touched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_field_min_max"
down_revision = "0022_stage_pct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("field_definitions", sa.Column("min_value", sa.Float(), nullable=True))
    op.add_column("field_definitions", sa.Column("max_value", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("field_definitions", "max_value")
    op.drop_column("field_definitions", "min_value")

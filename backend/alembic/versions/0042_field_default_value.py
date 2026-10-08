"""A Pick List field can have a default value — set in Setup

Revision ID: 0042_field_default_value
Revises: 0039_metadata_v2_enforce
Create Date: 2026-10-05

Zoho's Pick List properties have "Select default value": the choice a new
record starts with, which the person can change before saving. Until now the
only defaults the CRM had were written in code — a new Lead's Currency was
USD in LeadCreatePage and again in the server's create_lead. Setup rebuild,
4d: the default is a property of the field on its module, edited in Setup and
published like any other.

One nullable column on the placement, holding the choice's key. Nothing is
filled here: the defaults that replace the code ones are set by
setup_step4d_metadata.py, which publishes them, so they reach the live app the
way every register change does.

Revises 0039, not 0041: 0040 and 0041 (the Dashboard's tables) are not on
this branch yet. When they are, point 0040 at this revision so there is one
head again.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_field_default_value"
down_revision = "0039_metadata_v2_enforce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0038 adds it too since 8 Oct 2026, for metadata_v2.py's sake — see there.
    if "default_value" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("field_placements")}:
        return
    op.add_column(
        "field_placements",
        sa.Column("default_value", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("field_placements", "default_value")

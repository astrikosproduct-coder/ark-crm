"""A field can be required when a record is created — set in Administration

Revision ID: 0037_required_on_create
Revises: 0036_drop_pre_round7_archive
Create Date: 2026-09-21

On Leads, Opportunities and Deals a required field is asked for when the
record leaves the field's stage, not on every save (decided 21 Sep 2026). A few
fields have to be there from the first save — a Lead needs a name and an End
Client to be a Lead at all. That list lived in spec/extensions.json
(`create_required`), which only a code change could edit. It is a placement
property now, "Required when creating", ticked in Administration and published
like any other rule. The four fields the list named are ticked here, so nothing
changes on the day this runs.

Accounts and Contacts are unaffected: every required field there is required
on every save, creating included.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_required_on_create"
down_revision = "0036_drop_pre_round7_archive"
branch_labels = None
depends_on = None

CARRIED = ("opportunity_name", "end_client", "bd_owner", "currency")


def upgrade() -> None:
    op.add_column(
        "field_placements",
        sa.Column("required_on_create", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        sa.text(
            "UPDATE field_placements SET required_on_create = true "
            "WHERE module_key = 'leads' AND api_name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True, value=list(CARRIED)))
    )


def downgrade() -> None:
    op.drop_column("field_placements", "required_on_create")

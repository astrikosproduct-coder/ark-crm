"""A field can be asked at a stage move rather than on a form — a register fact

Revision ID: 0043_asked_at_stage_move
Revises: 0042_field_default_value
Create Date: 2026-10-05

Stage Skip Reason and Stage Reversal Reason are written by the Update Stage
dialog and by nothing else: no form offers a box for them, the Reasons &
Justifications panel lists them, and the server never demands them of a save.
Which fields behave like that was a hand-kept list in spec/extensions.json
(`stage_scoped.history_only`) that the form, the panel and the server each
read — and Setup could not see at all, so the layout editor showed both
reasons in Aging, where no record ever draws them.

Setup rebuild, 4e: it is a property of the field's placement, published like
any other, and Setup's layout editor shows those fields on a Stage move tab.
Nothing is set here: setup_step4e_metadata.py marks the two reasons and
publishes, and the sidecar list is removed in the same step.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_asked_at_stage_move"
down_revision = "0042_field_default_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0038 adds it too since 8 Oct 2026, for metadata_v2.py's sake — see there.
    if "asked_at_stage_move" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("field_placements")}:
        return
    op.add_column(
        "field_placements",
        sa.Column("asked_at_stage_move", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("field_placements", "asked_at_stage_move")

"""A stage move records the readiness checks a person ticked

Revision ID: 0021_attested
Revises: 0020_pursuit_groups
Create Date: 2026-09-13

Criteria the expression engine cannot evaluate — prose sources, attestations,
signatures, a gate whose module is not built — used to sit unticked in the
readiness panel with nothing anyone could do about them, and the Update Stage
button ignored them. From now on a forward move needs every one of them ticked
in the dialog, and the codes ticked are kept on the transition itself:
stage_transitions already stamps WHO (actor, from the session) and WHEN (the
server clock), which is exactly what an attestation needs and no second table
would add.

A JSONB list of criterion codes (["X3.2", "E4.1", "G2"]), empty for a move that
needed none. Existing rows become [] — nothing was attested before this.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021_attested"
down_revision = "0020_pursuit_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stage_transitions",
        sa.Column("attested", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("stage_transitions", "attested")

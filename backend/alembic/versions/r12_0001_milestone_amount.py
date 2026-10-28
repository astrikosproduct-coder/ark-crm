"""Payment milestones: an Amount beside the %, and a name for an "Other" milestone

Revision ID: r12_0001_milestone_amount
Revises: r11_0003_user_view_preferences
Create Date: 2026-10-28

v1.2.2 (28 Oct 2026, the head's ask): a milestone carries its VALUE as well as its
percentage of the contract — type one and the other is worked out — and the head
may add a milestone of their own beside the eight standard ones, so a row can name
itself. The Trigger text stops being typed per row (it is the hover message on each
standard milestone now).

  amount        the milestone's value, in the Opportunity's currency
  custom_name   the name of an "Other" milestone
  entered_as    which of Amount / % the person typed ('amount' | 'pct') — the
                one that stays fixed if the contract value moves later

`trigger` is kept as a column: what was typed stays in the database, it is only no
longer drawn or written. Nothing is dropped.

DEPLOY ORDER: dump -> alembic upgrade head -> release_1_2_2_metadata.py --apply
-> start the new code. (Never start the new code first: create_all would not add
these columns to an existing table.)

MERGING INTO PHASE 2: phase 2's 0038 also revises r11_0003. Point 0038's
down_revision at this revision so there is one head.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r12_0001_milestone_amount"
down_revision = "r11_0003_user_view_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunity_payment_milestones", sa.Column("amount", sa.Numeric(18, 2), nullable=True))
    op.add_column("opportunity_payment_milestones", sa.Column("custom_name", sa.String(120), nullable=True))
    op.add_column("opportunity_payment_milestones", sa.Column("entered_as", sa.String(6), nullable=True))
    op.create_check_constraint(
        "ck_payment_milestones_entered_as",
        "opportunity_payment_milestones",
        "entered_as IS NULL OR entered_as IN ('amount', 'pct')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_milestones_entered_as", "opportunity_payment_milestones", type_="check")
    op.drop_column("opportunity_payment_milestones", "entered_as")
    op.drop_column("opportunity_payment_milestones", "custom_name")
    op.drop_column("opportunity_payment_milestones", "amount")

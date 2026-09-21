"""Submission Deadline and Bid Submission Date are dates, not timestamps

Revision ID: 0029_bid_dates_are_dates
Revises: 0028_registration_currency
Create Date: 2026-09-16

Both were DateTime(timezone=True) and are now Date, on instruction (16 Sep
2026): a bid deadline is a DAY, and the time of day was never used by anything
— not the dashboard's due-window, not X4.1, not a list column.

It also removes a real defect. The API returned "2027-02-14T17:23:00+00:00",
and a browser's datetime-local box only accepts "2027-02-14T17:23" — given the
offset it renders EMPTY. The two fields therefore went blank in the form after
every save, which reads as data loss: it is what made OPP-00003's Feb 2027
values get retyped on 15 Sep. A date box takes "2027-02-14" as it stands.

EXISTING VALUES ARE TRUNCATED TO THE UTC DAY, explicitly rather than by the
session's TimeZone, so the result does not depend on who runs it. OPP-00003's
2026-09-15T20:30Z becomes 2026-09-15. A value stored from a late-evening local
entry can therefore land a day before what was typed — one record is affected
and its dates were already retyped once; confirm both against the tender.

DEPLOY ORDER:
    alembic upgrade head
    python bid_dates_to_date.py --apply     (retypes the register and publishes)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_bid_dates_are_dates"
down_revision = "0028_registration_currency"
branch_labels = None
depends_on = None

COLUMNS = ("submission_deadline", "bid_submission_date")


def upgrade() -> None:
    for column in COLUMNS:
        op.alter_column(
            "opportunities",
            column,
            type_=sa.Date(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using=f"({column} AT TIME ZONE 'UTC')::date",
        )


def downgrade() -> None:
    # Midnight UTC — the time of day is gone and cannot be recovered.
    for column in COLUMNS:
        op.alter_column(
            "opportunities",
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.Date(),
            existing_nullable=True,
            postgresql_using=f"{column}::timestamptz",
        )

"""Expected Timeline becomes a date

Revision ID: 0026_expected_timeline_date
Revises: 0025_partner_lifecycle
Create Date: 2026-09-14

deal_registrations.expected_timeline was free text ("RFP Q1 2027, award Q3
2027"). As of 14 Sep 2026 it is a date.

Existing text is NOT guessed into a date. A value that already is an ISO date
(YYYY-MM-DD) converts. Anything else is kept word for word in
expected_timeline_text, which no form shows, and Expected Timeline is left
blank for a person to fill. The upgrade prints which registrations those are.

DEPLOY ORDER — all of it, or the form and the column disagree:
    alembic upgrade head
    python expected_timeline_metadata.py --apply     (changes the register and publishes)
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0026_expected_timeline_date"
down_revision = "0025_partner_lifecycle"
branch_labels = None
depends_on = None

TABLE = "deal_registrations"


def upgrade() -> None:
    op.alter_column(TABLE, "expected_timeline", new_column_name="expected_timeline_text")
    op.add_column(TABLE, sa.Column("expected_timeline", sa.Date(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT registration_id, project_name, expected_timeline_text FROM {TABLE} "
            "WHERE expected_timeline_text IS NOT NULL AND btrim(expected_timeline_text) <> '' "
            "ORDER BY registration_id"
        )
    ).all()

    kept: list[str] = []
    for registration_id, project_name, text in rows:
        try:
            value = date.fromisoformat(text.strip())
        except ValueError:
            kept.append(f"    {project_name or registration_id}: {text.strip()!r}")
            continue
        bind.execute(
            sa.text(
                f"UPDATE {TABLE} SET expected_timeline = :value, expected_timeline_text = NULL "
                "WHERE registration_id = :id"
            ),
            {"value": value, "id": registration_id},
        )

    if kept:
        print(f"  Expected Timeline is blank on {len(kept)} registration(s); their old text is kept:")
        print("\n".join(kept))


def downgrade() -> None:
    # A date entered since the upgrade wins over the old text it replaced.
    op.execute(
        f"UPDATE {TABLE} SET expected_timeline_text = to_char(expected_timeline, 'YYYY-MM-DD') "
        "WHERE expected_timeline IS NOT NULL"
    )
    op.drop_column(TABLE, "expected_timeline")
    op.alter_column(TABLE, "expected_timeline_text", new_column_name="expected_timeline")

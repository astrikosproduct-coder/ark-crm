"""Partner lifecycle: withdrawal, conflict memory, adjudication evidence, a real lead link

Revision ID: 0025_partner_lifecycle
Revises: 0024_partner_stamps
Create Date: 2026-09-14

Storage for the Partners module decisions of 14 Sep 2026. The REGISTER half
(Withdrawn, "Partner withdrew", the three criteria picklists and the four new
field placements) is partner_lifecycle_metadata.py, run after this.

DEPLOY ORDER — all three, or the screens and the database disagree:
    alembic upgrade head
    python partner_lifecycle_metadata.py --apply
    python regenerate_spec.py --apply

1. deal_registrations.withdrawn_date / withdrawal_reason — set only by
   POST /registrations/{id}/withdraw. See app/registration_withdrawal.py.

2. deal_registrations.not_conflict_with / not_conflict_reason — the pairs a
   person declared "a different project", so the conflict check never asks
   about them again. See app/registration_matching.py.

3. registration_conflicts.decision_rationale / evidence_link — the proof
   behind an adjudication. A decision cannot be saved without the rationale.

4. leads.partner_deal_registration becomes a REAL foreign key, ON DELETE
   RESTRICT. It was a plain string: deleting a registration left its lead
   pointing at nothing. The upgrade refuses to run while any lead already
   points at a registration that does not exist, and names them — silently
   blanking a reference is a data change nobody asked for.

5. The three adjudication criteria become picklists. Existing free text is
   NOT thrown away and NOT guessed into a picklist value: it is moved into
   decision_rationale, labelled by criterion, and the two judgement criteria
   are left blank for the BD Director to pick. Who Registered First is
   recomputed from the two Submitted Dates, which is what it now always is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_partner_lifecycle"
down_revision = "0024_partner_stamps"
branch_labels = None
depends_on = None

FK_NAME = "fk_leads_partner_deal_registration"

WHO_KEYS = {"REGISTRATION_A", "REGISTRATION_B", "SAME_DAY"}
RELATIONSHIP_KEYS = {"REGISTRATION_A", "REGISTRATION_B", "COMPARABLE", "NEITHER"}

CRITERIA_LABELS = (
    ("who_registered_first", "Who registered first", WHO_KEYS),
    ("stronger_client_relationship", "Stronger client relationship", RELATIONSHIP_KEYS),
    ("better_delivery_capability", "Better delivery capability", RELATIONSHIP_KEYS),
)


def upgrade() -> None:
    op.add_column("deal_registrations", sa.Column("withdrawn_date", sa.Date(), nullable=True))
    op.add_column("deal_registrations", sa.Column("withdrawal_reason", sa.Text(), nullable=True))
    op.add_column("deal_registrations", sa.Column("not_conflict_reason", sa.Text(), nullable=True))
    op.add_column(
        "deal_registrations",
        sa.Column(
            "not_conflict_with",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("registration_conflicts", sa.Column("decision_rationale", sa.Text(), nullable=True))
    op.add_column("registration_conflicts", sa.Column("evidence_link", sa.String(500), nullable=True))

    bind = op.get_bind()

    dangling = bind.execute(
        sa.text(
            "SELECT lead_id, partner_deal_registration FROM leads "
            "WHERE partner_deal_registration IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM deal_registrations r WHERE r.registration_id = leads.partner_deal_registration)"
        )
    ).all()
    if dangling:
        listed = ", ".join(f"{lead} -> {reg}" for lead, reg in dangling[:20])
        raise RuntimeError(
            f"{len(dangling)} lead(s) name a deal registration that does not exist ({listed}). "
            "Correct or clear Partner Deal Registration on them, then run the upgrade again."
        )
    op.create_foreign_key(
        FK_NAME,
        "leads",
        "deal_registrations",
        ["partner_deal_registration"],
        ["registration_id"],
        ondelete="RESTRICT",
    )

    rows = bind.execute(
        sa.text(
            "SELECT c.conflict_id, c.who_registered_first, c.stronger_client_relationship, "
            "c.better_delivery_capability, c.decision_rationale, "
            "ra.submitted_date AS a_date, rb.submitted_date AS b_date "
            "FROM registration_conflicts c "
            "LEFT JOIN deal_registrations ra ON ra.registration_id = c.registration_a "
            "LEFT JOIN deal_registrations rb ON rb.registration_id = c.registration_b"
        )
    ).mappings().all()

    for row in rows:
        notes = []
        values = {}
        for column, label, keys in CRITERIA_LABELS:
            text = (row[column] or "").strip()
            if text and text not in keys:
                notes.append(f"{label}: {text}")
                values[column] = None
            else:
                values[column] = text or None

        if row["a_date"] and row["b_date"]:
            values["who_registered_first"] = (
                "REGISTRATION_A"
                if row["a_date"] < row["b_date"]
                else "REGISTRATION_B"
                if row["b_date"] < row["a_date"]
                else "SAME_DAY"
            )
        else:
            values["who_registered_first"] = None

        rationale = (row["decision_rationale"] or "").strip()
        if notes:
            carried = "Assessment recorded before the criteria became picklists:\n" + "\n".join(notes)
            rationale = f"{rationale}\n\n{carried}" if rationale else carried

        bind.execute(
            sa.text(
                "UPDATE registration_conflicts SET who_registered_first = :who, "
                "stronger_client_relationship = :stronger, better_delivery_capability = :better, "
                "decision_rationale = :rationale WHERE conflict_id = :id"
            ),
            {
                "who": values["who_registered_first"],
                "stronger": values["stronger_client_relationship"],
                "better": values["better_delivery_capability"],
                "rationale": rationale or None,
                "id": row["conflict_id"],
            },
        )


def downgrade() -> None:
    # The criteria text carried into decision_rationale is not split back out:
    # it stays readable in the rationale until the column is dropped, and a
    # downgrade is expected to be run from a backup taken before 0025.
    op.drop_constraint(FK_NAME, "leads", type_="foreignkey")
    op.drop_column("registration_conflicts", "evidence_link")
    op.drop_column("registration_conflicts", "decision_rationale")
    op.drop_column("deal_registrations", "not_conflict_with")
    op.drop_column("deal_registrations", "not_conflict_reason")
    op.drop_column("deal_registrations", "withdrawal_reason")
    op.drop_column("deal_registrations", "withdrawn_date")

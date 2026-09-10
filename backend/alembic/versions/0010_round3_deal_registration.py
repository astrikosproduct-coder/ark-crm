"""Round 3 (done out of order): deal_registrations, registration_conflicts

Revision ID: 0010_round3_registration
Revises: 0009_round7_audit
Create Date: 2026-09-04

Two ordinary business tables, editable through their own record forms — NOT
audit-log-shaped like Round 7's three tables. Neither has a sheet of its own
in the field register: the workbook describes both under the `partners`
module, in its DEAL REGISTRATION and CONFLICT ADJUDICATION sections (see
spec/extensions.json's `registrations.$note` and MODULE_OF_COLLECTION in
src/lib/spec/index.ts).

All lookup columns are ON DELETE SET NULL, matching Lead.end_client and
Contact.account: `Mandatory` in the register is a form-engine rule, not a
storage constraint, everywhere else in this schema — deal_registrations and
registration_conflicts follow the same rule rather than inventing a stricter
one for themselves.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_round3_registration"
down_revision = "0009_round7_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------ deal_registrations
    op.create_table(
        "deal_registrations",
        sa.Column("registration_id", sa.String(length=20), nullable=False),
        sa.Column("partner", sa.String(length=20), nullable=True),
        sa.Column("end_client", sa.String(length=20), nullable=True),
        sa.Column("project_name", sa.String(length=150), nullable=True),
        sa.Column("estimated_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_timeline", sa.String(length=100), nullable=True),
        sa.Column("partner_role", sa.String(length=40), nullable=True),
        sa.Column("submitted_date", sa.Date(), nullable=True),
        sa.Column("acknowledged_date", sa.Date(), nullable=True),
        sa.Column("acknowledgement_sla_met", sa.Boolean(), nullable=True),
        sa.Column("exclusivity_start_date", sa.Date(), nullable=True),
        sa.Column("exclusivity_expiry_date", sa.Date(), nullable=True),
        sa.Column("registration_status", sa.String(length=40), nullable=True),
        sa.Column("extension_reason", sa.String(length=500), nullable=True),
        sa.Column("linked_lead", sa.String(length=20), nullable=True),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("registration_id"),
        sa.ForeignKeyConstraint(["partner"], ["accounts.account_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["end_client"], ["accounts.account_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_lead"], ["leads.lead_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_deal_registrations_partner", "deal_registrations", ["partner"])
    op.create_index("ix_deal_registrations_end_client", "deal_registrations", ["end_client"])
    op.create_index("ix_deal_registrations_linked_lead", "deal_registrations", ["linked_lead"])

    # ------------------------------------------------- registration_conflicts
    op.create_table(
        "registration_conflicts",
        sa.Column("conflict_id", sa.String(length=20), nullable=False),
        sa.Column("registration_a", sa.String(length=20), nullable=True),
        sa.Column("registration_b", sa.String(length=20), nullable=True),
        sa.Column("who_registered_first", sa.String(length=300), nullable=True),
        sa.Column("stronger_client_relationship", sa.String(length=300), nullable=True),
        sa.Column("better_delivery_capability", sa.String(length=300), nullable=True),
        sa.Column("decision", sa.String(length=40), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("decided_by", sa.String(length=20), nullable=True),
        sa.Column(
            "both_partners_notified", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("conflict_id"),
        sa.ForeignKeyConstraint(
            ["registration_a"], ["deal_registrations.registration_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["registration_b"], ["deal_registrations.registration_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["decided_by"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_registration_conflicts_registration_a", "registration_conflicts", ["registration_a"]
    )
    op.create_index(
        "ix_registration_conflicts_registration_b", "registration_conflicts", ["registration_b"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_registration_conflicts_registration_b", table_name="registration_conflicts"
    )
    op.drop_index(
        "ix_registration_conflicts_registration_a", table_name="registration_conflicts"
    )
    op.drop_table("registration_conflicts")

    op.drop_index("ix_deal_registrations_linked_lead", table_name="deal_registrations")
    op.drop_index("ix_deal_registrations_end_client", table_name="deal_registrations")
    op.drop_index("ix_deal_registrations_partner", table_name="deal_registrations")
    op.drop_table("deal_registrations")

"""Round 7: stage_transitions, conversions, audit_log

Revision ID: 0009_round7_audit
Revises: 0008_placements
Create Date: 2026-09-04

Three audit-log-shaped tables, none of them register data — they record what
happened to a business row, not what the row contains:

    stage_transitions  every recorded pipeline stage move (skip/reversal +
                        reason), replacing the browser-only `transitions`
                        collection POSTed to today by AdvanceStageDialog.tsx,
                        LeadAdvanceDialog.tsx and DealDetailPage.tsx
    conversions         every Lead->Opportunity / Opportunity->Deal
                        conversion, replacing the browser-only `conversions`
                        collection POSTed to by LeadAdvanceDialog.tsx and
                        opportunities/ConvertToDealDialog.tsx
    audit_log           a new record-level CRUD trail across leads,
                        opportunities, deals, accounts and contacts, written
                        from inside those routers' own handlers
                        (app/audit.py) — never had a browser-store collection

None of the three carries a foreign key on its record-identifying columns
(record_id, source_id/target_id): each row's `module` (or
source_module/target_module) column says which of five different tables the
id belongs to, and no single FK can point at five parents. This mirrors
parent_lead/parent_opportunity's own reasoning on Deal for columns that
predate the target table existing, except here it is permanent, not
transitional.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_round7_audit"
down_revision = "0008_placements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------- stage_transitions
    op.create_table(
        "stage_transitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference_id", sa.String(length=20), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("record_id", sa.String(length=20), nullable=False),
        sa.Column("from_stage", sa.Integer(), nullable=False),
        sa.Column("to_stage", sa.Integer(), nullable=False),
        sa.Column("is_skip", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_reversal", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=20), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_id", name="uq_stage_transitions_reference_id"),
        sa.ForeignKeyConstraint(["actor"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_stage_transitions_record_id", "stage_transitions", ["record_id"]
    )

    # ------------------------------------------------------------ conversions
    op.create_table(
        "conversions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference_id", sa.String(length=20), nullable=False),
        sa.Column("source_module", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(length=20), nullable=False),
        sa.Column("target_module", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=20), nullable=False),
        sa.Column(
            "copied_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=20), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_id", name="uq_conversions_reference_id"),
        sa.ForeignKeyConstraint(["actor"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_conversions_source_id", "conversions", ["source_id"])
    op.create_index("ix_conversions_target_id", "conversions", ["target_id"])

    # ------------------------------------------------------------ audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference_id", sa.String(length=20), nullable=False),
        sa.Column("record_module", sa.String(length=20), nullable=False),
        sa.Column("record_id", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("actor", sa.String(length=20), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_id", name="uq_audit_log_reference_id"),
        sa.ForeignKeyConstraint(["actor"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_record_id", "audit_log", ["record_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_record_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_conversions_target_id", table_name="conversions")
    op.drop_index("ix_conversions_source_id", table_name="conversions")
    op.drop_table("conversions")

    op.drop_index("ix_stage_transitions_record_id", table_name="stage_transitions")
    op.drop_table("stage_transitions")

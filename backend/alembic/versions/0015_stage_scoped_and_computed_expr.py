"""Per-stage values, and the expression a computed field actually runs

Revision ID: 0015_stage_scoped
Revises: 0014_close_month
Create Date: 2026-09-10

Two vocabulary gaps, both of which made an admin ask me to edit a file.

    field_placements.stage_scoped     one value, or one per stage
    field_definitions.computed_expr   the expression the engine evaluates

Nothing moves here. Both columns land NULL/'none' on every existing row; the
values are backfilled from spec/extensions.json by absorb_sidecar.py, which is
data and goes through the API's own validation the way anchor_reasons.py did.

1. stage_scoped
---------------
A field whose value is recorded PER STAGE rather than once per record, stored
as `<api_name>__s<stage>` in custom_fields. The register has never had a column
for this. spec/extensions.json's own open_questions entry says so in as many
words — "ACTION REQUIRED - SPEC UPDATE. A NEW STORAGE CONCEPT THE REGISTER HAS
NO COLUMN FOR ... The workbook needs a column - `stage_scoped: none |
carry_forward | sticky` - or these five CROSS-CUTTING rows plus probability_pct
and progression_pct will regenerate as ordinary single-value fields."

    none            the default. One value per record.
    carry_forward   a stage with no value of its own INHERITS the nearest
                    earlier stage that has one. Progression %, Probability %,
                    Expected Close Month. The base api_name also holds the
                    current answer, so list views and the readiness engine keep
                    reading one number.
    sticky          captured at the stage where its condition became true, and
                    NEVER carried. On Hold Reason at Stage 1 and again at Stage
                    3 is two different answers; the Stage 3 box opens empty.
                    The base api_name is never written.

ON THE PLACEMENT, NOT THE DEFINITION, and that is the point: Deals was
deliberately excluded from the metrics strip while Leads and Opportunities
carry it, so probability_pct is per-stage on two modules and record-level on
the third. One column on the definition could not say that. It is the same
reasoning value_mode already follows.

WHY NOT A CHECK THAT ONLY PIPELINE MODULES MAY SET IT
------------------------------------------------------
Because `stage_scoped <> 'none'` on a module with no stages is meaningless
rather than corrupt, and the module a placement is on is not a column this
CHECK could reach without a join. The API refuses it where the module is known;
src/lib/stageScope.ts ignores it on a module that renders no stages, which is
the behaviour a dangling anchor already gets.

2. computed_expr
----------------
`computed_formula` already exists and is NOT this. It holds the register's own
English sentence — "One-Time + (Annual x 3)", "Start date plus 90 days" — and
it is rendered to the user as help text under the field.

The expression the engine evaluates has lived in spec/extensions.json as
`computed_expr` — `one_time_cost + annual_recurring * 3`. Twenty-eight of them.

These are two different things and BOTH are wanted on screen. FieldRow.tsx says
why, and it is the sharpest thing in the codebase about what this prototype is
for: partners.exclusivity_expiry_date shows the register's "Start date plus 90
days" beside an engine that computes `add_days(..., 89)`, and "a reviewer needs
to see both, not be quietly shown the corrected one." The disagreement IS the
finding. Folding one into the other would delete it.

So: a second column, not a rename. An admin creating a computed field can then
type an expression that runs — which today they cannot, and the field renders a
blank row forever. The register has 22 such rows right now, and Close Date
Pushback Count was deleted last week for exactly that.

No CHECK that computed_expr implies field_type='computed'. A non-computed field
with an expression is inert rather than wrong, and the publish validator is
where that judgement belongs — it can say which field and why, which a CHECK
constraint cannot.
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_stage_scoped"
down_revision = "0014_close_month"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "field_placements",
        sa.Column(
            "stage_scoped",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_check_constraint(
        "ck_field_placements_stage_scoped",
        "field_placements",
        "stage_scoped IN ('none', 'carry_forward', 'sticky')",
    )
    # "Which fields on this module are per-stage" is asked once per record load,
    # by the projection in useRecordForm and by the metrics strip. Partial,
    # because it is a dozen rows out of 672 and an index over a column that is
    # 98% one value would be ignored.
    op.create_index(
        "ix_field_placements_stage_scoped",
        "field_placements",
        ["module_key", "stage_scoped"],
        postgresql_where=sa.text("stage_scoped <> 'none'"),
    )

    op.add_column("field_definitions", sa.Column("computed_expr", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("field_definitions", "computed_expr")
    op.drop_index("ix_field_placements_stage_scoped", table_name="field_placements")
    op.drop_constraint("ck_field_placements_stage_scoped", "field_placements")
    op.drop_column("field_placements", "stage_scoped")

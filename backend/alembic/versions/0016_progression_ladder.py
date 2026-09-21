"""The progression ladder: two rule tables, and the columns they drive

Revision ID: 0016_progression
Revises: 0015_stage_scoped
Create Date: 2026-09-10

Progression % and Probability % stop being two numbers a BD manager types and
become a function of the evidence already on the record. See app/progression.py
for the evaluator; this is the schema underneath it.

FOUR THINGS HAPPEN HERE, AND THREE OF THEM ARE REPAIRS
-------------------------------------------------------

1. TWO RULE TABLES
   progression_criteria (sixteen rungs) and rung_proof_conditions (the evidence
   each demands). Data, not code, for the reason CLAUDE.md gives and the
   ProgressionCriterion docstring elaborates: the percentages are the thing the
   prototype exists to find out are wrong.

2. NINE COLUMNS ON EACH PIPELINE TABLE
   The rung a record sits on, the snapshot of what that rung said when it was
   entered, and the audited override. Not register fields — see
   ProgressionLadderMixin.

3. progression_pct / probability_pct: Integer -> Numeric(5,4)
   THE VALUES CHANGE MEANING AND THE DATA IS CONVERTED, not cast. The columns
   held whole numbers (43 meant 43%); they now hold fractions (0.4300), because
   the ladder is defined in fractions and 0.155 is a legal probability that
   15.5 could not be stored as. Every existing row is divided by 100.

   The downgrade multiplies back and ROUNDS, which loses any fraction finer
   than a whole percent. Said plainly here because a downgrade that silently
   rounds is worse than one that refuses, and this one is recoverable only
   because nothing in the shipped ladder issues a value finer than 0.05.

4. THREE COLUMNS THE REGISTER ALREADY DECLARED AND NO TABLE HAD
   leads.agreed_next_step, deals.contract_signed_date, and Deals' own
   progression_pct / probability_pct. All four have active placements with
   storage='column' and had nowhere to store anything, so every value written
   to them was dropped on save.

   This is not scope creep. agreed_next_step is R_POC's only proof AND the
   visibility gate for pilot_commercial_model and pilot_fee, so without it the
   paid-POC rule in Part 3c can never fire and three Stage-1 boxes render off a
   control that cannot be set. contract_signed_date is R14's only proof. A
   ladder whose top rung and whose POC rung are both unreachable is not a
   ladder.

   deals.lead_status has the same problem and is NOT fixed here — nothing in
   the ladder reads it, so it stays where models.Deal's note left it.

5. ONE PICKLIST VALUE
   deals__deal_stage gains 'POC / Pilot Deal'. Part 3c is explicit that this is
   a new permitted value on the EXISTING deal_stage field and not a new column,
   and picklist values are rows, so it is an insert into picklist_values rather
   than anything structural. Written here rather than in the seed script
   because the paid-POC Deal cannot be created without it.

WHY THE PERCENTAGE COLUMNS ARE NOT DROPPED AND REBUILT
-------------------------------------------------------
ALTER ... TYPE ... USING keeps the column, its position, and every grant and
comment on it. Dropping and re-adding would move it to the end of the table,
which nothing depends on, and would lose the data, which everything does.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_progression"
down_revision = "0015_stage_scoped"
branch_labels = None
depends_on = None

#: The three tables the ladder runs on. Every column below lands on all three,
#: because a pursuit's rung has to survive Lead -> Opportunity -> Deal.
PIPELINE_TABLES = ("leads", "opportunities", "deals")


def upgrade() -> None:
    # gen_random_uuid() is core since PostgreSQL 13, but the extension is free
    # to create and makes the default work on an older server too.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ------------------------------------------------------------- 1. rules
    op.create_table(
        "progression_criteria",
        sa.Column("code", sa.String(length=10), primary_key=True),
        sa.Column("rung_name", sa.String(length=120), nullable=False),
        sa.Column("progression_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("probability_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "progression_pct >= 0 AND progression_pct <= 1",
            name="ck_progression_criteria_progression_range",
        ),
        sa.CheckConstraint(
            "probability_pct >= 0 AND probability_pct <= 1",
            name="ck_progression_criteria_probability_range",
        ),
    )

    op.create_table(
        "rung_proof_conditions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "rung_code",
            sa.String(length=10),
            sa.ForeignKey("progression_criteria.code", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("field_api", sa.String(length=80), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("compare_value", sa.Text(), nullable=True),
        sa.Column("join_group", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("related_module", sa.String(length=30), nullable=True),
        sa.Column("related_field", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "operator IN ('IS_TRUE', 'IS_NOT_NULL', 'EQUALS', 'NOT_EQUALS')",
            name="ck_rung_proof_conditions_operator",
        ),
        # EQUALS with nothing to equal is a rule that can never be satisfied,
        # and it looks identical to a rung nobody has reached. Refused at the
        # constraint so a seed typo fails loudly at insert.
        sa.CheckConstraint(
            "operator IN ('IS_TRUE', 'IS_NOT_NULL') OR compare_value IS NOT NULL",
            name="ck_rung_proof_conditions_compare_value",
        ),
        sa.CheckConstraint(
            "(related_module IS NULL) = (related_field IS NULL)",
            name="ck_rung_proof_conditions_related_pair",
        ),
    )

    # -------------------------------------------------- 2/3. pipeline tables
    for table in PIPELINE_TABLES:
        # Deals never had these two at all — the gap models.Deal's deal_stage
        # note describes. Adding rather than altering there.
        if table == "deals":
            op.add_column(table, sa.Column("progression_pct", sa.Numeric(5, 4), nullable=True))
            op.add_column(table, sa.Column("probability_pct", sa.Numeric(5, 4), nullable=True))
        else:
            for column in ("progression_pct", "probability_pct"):
                op.execute(
                    f"ALTER TABLE {table} "
                    f"ALTER COLUMN {column} TYPE numeric(5,4) "
                    f"USING (CASE WHEN {column} IS NULL THEN NULL "
                    f"            ELSE LEAST({column}::numeric / 100, 1) END)"
                )

        op.add_column(
            table,
            sa.Column(
                "current_rung_code",
                sa.String(length=10),
                sa.ForeignKey("progression_criteria.code", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_current_rung_code", table, ["current_rung_code"])

        op.add_column(table, sa.Column("progression_default_pct", sa.Numeric(5, 4), nullable=True))
        op.add_column(table, sa.Column("probability_default_pct", sa.Numeric(5, 4), nullable=True))
        op.add_column(
            table,
            sa.Column(
                "is_overridden", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )
        op.add_column(table, sa.Column("override_justification", sa.Text(), nullable=True))
        op.add_column(
            table,
            sa.Column(
                "overridden_by",
                sa.String(length=20),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(
            table, sa.Column("overridden_date", sa.DateTime(timezone=True), nullable=True)
        )
        op.add_column(
            table,
            sa.Column(
                "needs_progression_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.add_column(table, sa.Column("progression_review_note", sa.Text(), nullable=True))

    # ------------------------------------------------- 4. the missing columns
    op.add_column("leads", sa.Column("agreed_next_step", sa.String(length=30), nullable=True))
    op.add_column("deals", sa.Column("contract_signed_date", sa.Date(), nullable=True))

    # ------------------------------------------------ 5. the picklist value
    # A row, not a schema change. Guarded so a re-run or a hand-added value
    # cannot collide on the (picklist_key, value_key) uniqueness.
    op.execute(
        """
        INSERT INTO picklist_values
               (picklist_key, key, label, sort_order, active, created_at, updated_at)
        SELECT 'deals__deal_stage', 'POC_PILOT_DEAL', 'POC / Pilot Deal',
               COALESCE(MAX(sort_order), 0) + 1, true, now(), now()
          FROM picklist_values
         WHERE picklist_key = 'deals__deal_stage'
           AND NOT EXISTS (
                 SELECT 1 FROM picklist_values
                  WHERE picklist_key = 'deals__deal_stage'
                    AND key = 'POC_PILOT_DEAL')
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM picklist_values "
        "WHERE picklist_key = 'deals__deal_stage' AND key = 'POC_PILOT_DEAL'"
    )

    op.drop_column("deals", "contract_signed_date")
    op.drop_column("leads", "agreed_next_step")

    for table in PIPELINE_TABLES:
        for column in (
            "progression_review_note",
            "needs_progression_review",
            "overridden_date",
            "overridden_by",
            "override_justification",
            "is_overridden",
            "probability_default_pct",
            "progression_default_pct",
        ):
            op.drop_column(table, column)
        op.drop_index(f"ix_{table}_current_rung_code", table_name=table)
        op.drop_column(table, "current_rung_code")

        if table == "deals":
            op.drop_column(table, "probability_pct")
            op.drop_column(table, "progression_pct")
        else:
            # ROUNDS. See the module docstring — anything finer than a whole
            # percent does not survive the trip back.
            for column in ("progression_pct", "probability_pct"):
                op.execute(
                    f"ALTER TABLE {table} "
                    f"ALTER COLUMN {column} TYPE integer "
                    f"USING (CASE WHEN {column} IS NULL THEN NULL "
                    f"            ELSE ROUND({column} * 100)::integer END)"
                )

    op.drop_table("rung_proof_conditions")
    op.drop_table("progression_criteria")

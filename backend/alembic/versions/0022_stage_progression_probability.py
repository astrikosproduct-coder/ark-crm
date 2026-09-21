"""One stage table drives Progression % and Probability %

Revision ID: 0022_stage_pct
Revises: 0021_attested
Create Date: 2026-09-13

DECIDED 13 Sep 2026 (ARK business decision): the stage IS the rung. Each of the
ten stages carries one Progression % and one Probability %, both multiples of
5, and a record takes that pair whenever it enters the stage. A person may
change either number, with a justification. See app/progression.py.

    Stage                    Prog  Prob   Prog = our work done   Prob = client decisions
    0 Connect                  5     5
    1 Demo Presentation       15    10
    2 POC / Pilot             25    20
    3 Prescription            40    30
    4 RFP / RFI               50    40
    5 Technical Evaluation    70    55
    6 Commercial Evaluation   85    70
    7 Close                   95    90
    8 Project Success        100   100
    9 Expansion              100   100

WHAT THIS REPLACES, AND IS REMOVED
----------------------------------
* The evidence ladder (0016): progression_criteria, rung_proof_conditions, and
  current_rung_code / needs_progression_review / progression_review_note on the
  three pipeline tables. It and the stage band both wrote the same two numbers
  and the last writer won.
* stages.prob_min / prob_max. A band is not a value; the single pair replaces it.
* Per-stage copies of the two numbers (`progression_pct__s<n>` in custom_fields).
  The number follows the stage now, so a carried-forward copy can only disagree
  with it. The justification stays per stage — it is written about one stage.

PAID POC / PILOT
----------------
'POC / Pilot Deal' stops being a Deal STAGE and becomes a Deal STATUS on the
shared status picklist (the server refuses it on Leads and Opportunities), and
the Deal sits at Stage 7 Close. deals__deal_stage gains the 7_CLOSE key it has
been missing since the pipeline split. The one existing pilot Deal is moved
across and its Lead, by the same decision, becomes Converted.

EVERY RECORD IS RESET TO ITS STAGE'S PAIR. Overrides made against the old
ladder were arguments about a rung that no longer exists; their written reasons
stay in custom_fields, so nothing a person typed is lost.

DOWNGRADE restores the schema and the bands, not the ladder's rows or the
records' old numbers — those are in backend/pre_0022_backup.sql.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_stage_pct"
down_revision = "0021_attested"
branch_labels = None
depends_on = None

PIPELINE_TABLES = ("leads", "opportunities", "deals")

#: stage -> (progression %, probability %). Whole percents, as the stages table
#: stores them; the record columns hold the fraction.
TABLE = {
    0: (5, 5),
    1: (15, 10),
    2: (25, 20),
    3: (40, 30),
    4: (50, 40),
    5: (70, 55),
    6: (85, 70),
    7: (95, 90),
    8: (100, 100),
    9: (100, 100),
}

#: The bands 0002 seeded, for the downgrade only.
BANDS = {0: (0, 10), 1: (10, 20), 2: (20, 40), 3: (30, 50), 4: (40, 60), 5: (50, 70),
         6: (60, 80), 7: (90, 100), 8: (100, 100), 9: (None, None)}

STAGE_FIELD = {"leads": "project_stage", "opportunities": "project_stage", "deals": "deal_stage"}

PER_STAGE_PCT_KEY = r"^(progression_pct|probability_pct)__s[0-9]+$"


def upgrade() -> None:
    # ------------------------------------------------------ 1. the one table
    op.add_column("stages", sa.Column("progression_pct", sa.Integer(), nullable=True))
    op.add_column("stages", sa.Column("probability_pct", sa.Integer(), nullable=True))
    for stage, (progression, probability) in TABLE.items():
        op.execute(
            f"UPDATE stages SET progression_pct = {progression}, probability_pct = {probability} "
            f"WHERE stage = {stage}"
        )
    for column in ("progression_pct", "probability_pct"):
        op.create_check_constraint(
            f"ck_stages_{column}_step",
            "stages",
            f"{column} IS NULL OR ({column} BETWEEN 0 AND 100 AND {column} % 5 = 0)",
        )
    op.drop_column("stages", "prob_min")
    op.drop_column("stages", "prob_max")

    # --------------------------------------------------- 2. the ladder, gone
    for table in PIPELINE_TABLES:
        op.drop_column(table, "progression_review_note")
        op.drop_column(table, "needs_progression_review")
        op.drop_column(table, "current_rung_code")  # drops its index and FK with it
    op.drop_table("rung_proof_conditions")
    op.drop_table("progression_criteria")

    # ------------------------------------------------------ 3. paid POC deal
    op.execute(
        "INSERT INTO picklist_values (picklist_key, key, label, sort_order, active, created_at, updated_at) "
        "SELECT 'deals__deal_stage', '7_CLOSE', 'Close', 0, true, now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM picklist_values "
        "                  WHERE picklist_key = 'deals__deal_stage' AND key = '7_CLOSE')"
    )
    op.execute(
        "INSERT INTO picklist_values (picklist_key, key, label, sort_order, active, created_at, updated_at) "
        "SELECT 'leads__lead_status', 'POC_PILOT_DEAL', 'POC/Pilot Deal', "
        "       COALESCE(MAX(sort_order), 0) + 1, true, now(), now() "
        "  FROM picklist_values WHERE picklist_key = 'leads__lead_status' "
        "HAVING NOT EXISTS (SELECT 1 FROM picklist_values "
        "                   WHERE picklist_key = 'leads__lead_status' AND key = 'POC_PILOT_DEAL')"
    )
    op.execute(
        "UPDATE leads SET lead_status = 'CONVERTED' "
        "WHERE lead_id IN (SELECT parent_lead FROM deals "
        "                  WHERE deal_stage = 'POC_PILOT_DEAL' AND parent_lead IS NOT NULL)"
    )
    op.execute(
        "UPDATE deals SET deal_stage = '7_CLOSE', lead_status = 'POC_PILOT_DEAL' "
        "WHERE deal_stage = 'POC_PILOT_DEAL'"
    )
    op.execute(
        "DELETE FROM picklist_values "
        "WHERE picklist_key = 'deals__deal_stage' AND key = 'POC_PILOT_DEAL'"
    )

    # ------------------------------------- 4. every record onto its stage pair
    for table in PIPELINE_TABLES:
        field = STAGE_FIELD[table]
        op.execute(
            f"""
            UPDATE {table} t
               SET progression_pct         = s.progression_pct / 100.0,
                   progression_default_pct = s.progression_pct / 100.0,
                   probability_pct         = s.probability_pct / 100.0,
                   probability_default_pct = s.probability_pct / 100.0,
                   is_overridden = false, overridden_by = NULL, overridden_date = NULL
              FROM stages s
             WHERE s.stage = substring(t.{field} from '^([0-9]+)')::int
            """
        )
        op.execute(
            f"UPDATE {table} SET probability_pct = 0, probability_default_pct = 0 "
            f"WHERE lead_status = 'CLOSED_LOST'"
        )
        op.execute(
            f"""
            UPDATE {table}
               SET custom_fields = (
                     SELECT COALESCE(jsonb_object_agg(e.key, e.value), '{{}}'::jsonb)
                       FROM jsonb_each(custom_fields) e
                      WHERE e.key !~ '{PER_STAGE_PCT_KEY}')
             WHERE custom_fields IS NOT NULL
               AND EXISTS (SELECT 1 FROM jsonb_object_keys(custom_fields) k
                            WHERE k ~ '{PER_STAGE_PCT_KEY}')
            """
        )
    op.execute(
        "UPDATE deals SET probability_pct = 1, probability_default_pct = 1 "
        "WHERE lead_status = 'POC_PILOT_DEAL'"
    )

    # ----------------------------------------------- 5. the register's words
    op.execute(
        "UPDATE field_placements SET stage_scoped = 'none' "
        "WHERE api_name IN ('progression_pct', 'probability_pct')"
    )
    _describe(
        "progression_pct",
        label="Progression %",
        values_note="Set from the stage: 5 · 15 · 25 · 40 · 50 · 70 · 85 · 95 · 100 · 100. Multiples of 5.",
        description="How much of the sales effort to signature is done. Set automatically whenever the record enters a stage.",
        use_case=(
            "Moves on OUR work. One value per stage, held on the Stages table in Administration. "
            "Changing it by hand needs Override Justification for the current stage."
        ),
    )
    _describe(
        "probability_pct",
        label="Probability (%)",
        values_note="Set from the stage: 5 · 10 · 20 · 30 · 40 · 55 · 70 · 90 · 100 · 100. Multiples of 5.",
        description="Likelihood of winning. Set automatically whenever the record enters a stage.",
        use_case=(
            "Moves on the CLIENT's decisions. One value per stage, held on the Stages table in "
            "Administration. Changing it by hand needs Override Justification for the current stage. "
            "Closed Lost is 0%; a POC/Pilot Deal is 100%."
        ),
    )
    _describe(
        "probability_override_justification",
        label="Override Justification",
        values_note=None,
        description="Why Progression % or Probability % differs from the value its stage sets.",
        use_case=(
            "Required whenever either number is changed away from the stage's value. Recorded "
            "against the stage it was written at and never carried forward."
        ),
    )


def _describe(api_name: str, *, label: str, values_note: str | None, description: str, use_case: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE field_definitions SET label = :label, values_note = :note, "
            "description = :description, use_case = :use_case, updated_at = now() "
            "WHERE scope_key = 'pipeline' AND api_name = :api_name"
        ),
        {"label": label, "note": values_note, "description": description,
         "use_case": use_case, "api_name": api_name},
    )


def downgrade() -> None:
    op.execute(
        "UPDATE field_placements SET stage_scoped = 'carry_forward' "
        "WHERE api_name IN ('progression_pct', 'probability_pct')"
    )

    op.execute(
        "INSERT INTO picklist_values (picklist_key, key, label, sort_order, active, created_at, updated_at) "
        "SELECT 'deals__deal_stage', 'POC_PILOT_DEAL', 'POC / Pilot Deal', 4, true, now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM picklist_values "
        "                  WHERE picklist_key = 'deals__deal_stage' AND key = 'POC_PILOT_DEAL')"
    )
    op.execute(
        "UPDATE deals SET deal_stage = 'POC_PILOT_DEAL', lead_status = 'OPEN' "
        "WHERE lead_status = 'POC_PILOT_DEAL'"
    )
    op.execute(
        "DELETE FROM picklist_values WHERE "
        "(picklist_key = 'leads__lead_status' AND key = 'POC_PILOT_DEAL') OR "
        "(picklist_key = 'deals__deal_stage' AND key = '7_CLOSE')"
    )

    op.create_table(
        "progression_criteria",
        sa.Column("code", sa.String(length=10), primary_key=True),
        sa.Column("rung_name", sa.String(length=120), nullable=False),
        sa.Column("progression_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("probability_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "rung_proof_conditions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rung_code", sa.String(length=10),
                  sa.ForeignKey("progression_criteria.code", ondelete="CASCADE"), nullable=False),
        sa.Column("field_api", sa.String(length=80), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("compare_value", sa.Text(), nullable=True),
        sa.Column("join_group", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("related_module", sa.String(length=30), nullable=True),
        sa.Column("related_field", sa.String(length=80), nullable=True),
    )
    for table in PIPELINE_TABLES:
        op.add_column(table, sa.Column(
            "current_rung_code", sa.String(length=10),
            sa.ForeignKey("progression_criteria.code", ondelete="SET NULL"), nullable=True))
        op.add_column(table, sa.Column(
            "needs_progression_review", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.add_column(table, sa.Column("progression_review_note", sa.Text(), nullable=True))

    op.add_column("stages", sa.Column("prob_min", sa.Integer(), nullable=True))
    op.add_column("stages", sa.Column("prob_max", sa.Integer(), nullable=True))
    for stage, (low, high) in BANDS.items():
        op.get_bind().execute(
            sa.text("UPDATE stages SET prob_min = :low, prob_max = :high WHERE stage = :stage"),
            {"low": low, "high": high, "stage": stage},
        )
    op.drop_constraint("ck_stages_probability_pct_step", "stages", type_="check")
    op.drop_constraint("ck_stages_progression_pct_step", "stages", type_="check")
    op.drop_column("stages", "probability_pct")
    op.drop_column("stages", "progression_pct")

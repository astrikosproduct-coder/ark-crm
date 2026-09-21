"""FX Rate at Entry is a hand-typed Text field, not a System number

Revision ID: 0019_fx_rate_free_text
Revises: 0018_audit_changed_values
Create Date: 2026-09-12

TWO REGISTER MISTAKES, FIXED TOGETHER.

1. `requirement = 'System'`. System means the application records the value —
   it is what Created By / Created Date / Modified By / Modified Date carry, and
   as of Sep 2026 the form engine renders System fields read-only because the
   server stamps them and discards anything a payload claims. Nothing has ever
   stamped fx_rate_at_entry. spec/extensions.json says so in as many words:
   "fx_rate_at_entry is typed by hand, so an INR lead is enterable but its USD
   reporting figure is only as good as the rate the user types." Marked System,
   it became a field nobody could fill in, which is the opposite of what the
   register meant. Now Optional.

2. `type = 'number'` on a numeric(12,6) column. A BD records what the rate WAS
   and where it came from, and a bare six-decimal number cannot carry that.
   Free text can. Nothing computes with this value — no computed_formula on any
   module references it, checked before writing this — so widening it costs no
   arithmetic.

THE COLUMN CHANGES WITH THE FIELD. Changing only the metadata would leave the
register promising text while the column rejected it: a BD typing "3.6725 (ADCB
spot, 12 Sep)" would get a 422 from Pydantic's float and never find out why.
numeric -> text preserves every existing value exactly.

DOWNGRADE IS NOT ALWAYS POSSIBLE, and says so rather than pretending. Once a
row holds text that is not a number, casting back to numeric fails. The
downgrade below uses a guarded cast that nulls anything unparseable — which is
lossy, and is the honest behaviour for a reversal that genuinely cannot be
clean.

deals has no fx_rate_at_entry column and is untouched.
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_fx_rate_free_text"
down_revision = "0018_audit_changed_values"
branch_labels = None
depends_on = None

#: The modules that actually carry the column. Deals never had one.
TABLES = ("leads", "opportunities")

API_NAME = "fx_rate_at_entry"


def upgrade() -> None:
    conn = op.get_bind()

    for table in TABLES:
        op.alter_column(
            table,
            API_NAME,
            type_=sa.Text(),
            existing_type=sa.Numeric(12, 6),
            existing_nullable=True,
            postgresql_using=f"{API_NAME}::text",
        )

    # The register itself — the source of truth the JSON is generated from.
    conn.execute(
        sa.text(
            "UPDATE field_definitions SET field_type = 'text', max_length = 100 "
            "WHERE api_name = :name"
        ),
        {"name": API_NAME},
    )
    conn.execute(
        sa.text(
            "UPDATE field_placements SET requirement = 'Optional', editable = true "
            "WHERE api_name = :name"
        ),
        {"name": API_NAME},
    )
    print(f"  [0019] {API_NAME}: number/System -> text/Optional on {', '.join(TABLES)}")
    print("  [0019] run `python regenerate_spec.py --apply` to refresh spec/fields.json")


def downgrade() -> None:
    conn = op.get_bind()

    for table in TABLES:
        # Anything that is not a plain number becomes NULL rather than failing
        # the whole migration. See the docstring — this direction is lossy.
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {API_NAME} TYPE numeric(12,6) "
            f"USING NULLIF(regexp_replace({API_NAME}, '[^0-9.]', '', 'g'), '')::numeric"
        )

    conn.execute(
        sa.text(
            "UPDATE field_definitions SET field_type = 'number', max_length = NULL "
            "WHERE api_name = :name"
        ),
        {"name": API_NAME},
    )
    conn.execute(
        sa.text("UPDATE field_placements SET requirement = 'System' WHERE api_name = :name"),
        {"name": API_NAME},
    )

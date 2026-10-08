"""Sales targets: one BD Owner's booking target per month, lockable, revised by a new row

Revision ID: 0040_sales_targets
Revises: 0043_asked_at_stage_move
Create Date: 2026-09-28

Dashboard Phase 1 (28 Sep 2026). The dashboard's budget line needs an amount
per month, and nothing in the schema could hold one. No column is added to any
existing table.

THE GRAIN IS OWNER x MONTH
    Region, segment and company targets are never stored. They are sums of the
    owners' rows, rolled up through each owner's deals, so a company target
    cannot be counted twice.

ONE CURRENT ROW PER (fiscal year, month, owner)
    `uq_sales_targets_current` is a partial unique index that ignores
    SUPERSEDED rows. A second target for the same owner and month is refused
    by the database, whichever path wrote it.

LOCKED IS ENFORCED HERE, NOT ONLY IN THE API
    `trg_sales_targets_guard`:
      - a DRAFT row may change freely, or be deleted;
      - a LOCKED row may take exactly one step, to SUPERSEDED, with every
        business column unchanged, and is never deleted;
      - a SUPERSEDED row never changes and is never deleted;
      - a row with `revision_of` may be inserted only once the row it revises
        is SUPERSEDED, and must keep that row's fiscal year, month and owner.
    So a change to a locked target is always a new, linked, noted row, and a
    mid-year revision stays visible beside the number it replaced.

    The brief asked for status draft | locked. SUPERSEDED is added because the
    unique index has to know which row is current, and a partial index cannot
    look at another row to find out. Values are upper-case keys, as every
    status in this schema is (OPEN, CLOSED_LOST, NEW).

`fiscal_year` is written by the server from `period_month` and the
FISCAL_YEAR_START_MONTH setting (app/fiscal.py); the database checks its shape
only, because it cannot read the setting.

Audit: every create, edit, lock and revision writes audit_log through
app/audit.py::record_audit, module 'sales_targets' (app/sales_targets.py).

PRE-CREATED TABLE
    app/main.py runs create_all on start-up, so a dev server that reloaded
    after models.py gained SalesTarget has already built this table, without
    its trigger. If it is empty it is dropped and built here properly; if it
    holds rows, this stops (0032's rule).

DEPLOY ORDER
    alembic upgrade head
    python seed_sales_targets.py --actor <email>            (dry run)
    python seed_sales_targets.py --actor <email> --apply    (FY27 rows, 0, draft)

DOWNGRADE drops the table and every target in it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_sales_targets"
down_revision = "0043_asked_at_stage_move"  # after Setup's 0042-0043 (one head, 8 Oct 2026)
branch_labels = None
depends_on = None

TABLE = "sales_targets"

GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION sales_targets_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    original sales_targets%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision_of IS NOT NULL THEN
            SELECT * INTO original FROM sales_targets WHERE target_id = NEW.revision_of;
            IF original.status IS DISTINCT FROM 'SUPERSEDED' THEN
                RAISE EXCEPTION 'sales target %: only a locked target is revised, and it is marked superseded first',
                    NEW.target_id USING ERRCODE = 'check_violation';
            END IF;
            IF (original.fiscal_year, original.period_month, original.bd_owner_id)
               IS DISTINCT FROM (NEW.fiscal_year, NEW.period_month, NEW.bd_owner_id) THEN
                RAISE EXCEPTION 'sales target %: a revision keeps the fiscal year, month and owner of %',
                    NEW.target_id, NEW.revision_of USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'sales target % is %: only a draft is ever deleted',
                OLD.target_id, lower(OLD.status) USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;

    -- UPDATE
    IF OLD.status = 'DRAFT' THEN
        IF NEW.status = 'SUPERSEDED' THEN
            RAISE EXCEPTION 'sales target %: a draft is edited, not superseded',
                OLD.target_id USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status = 'LOCKED' AND NEW.status = 'SUPERSEDED'
       AND (NEW.target_id, NEW.fiscal_year, NEW.period_month, NEW.bd_owner_id, NEW.target_amount_usd,
            NEW.currency, NEW.locked_at, NEW.locked_by, NEW.revision_of, NEW.revision_note,
            NEW.created_at, NEW.created_by)
           IS NOT DISTINCT FROM
           (OLD.target_id, OLD.fiscal_year, OLD.period_month, OLD.bd_owner_id, OLD.target_amount_usd,
            OLD.currency, OLD.locked_at, OLD.locked_by, OLD.revision_of, OLD.revision_note,
            OLD.created_at, OLD.created_by) THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'sales target % is %: it never changes; revise it instead',
        OLD.target_id, lower(OLD.status) USING ERRCODE = 'check_violation';
END;
$$;
"""


def _create_table() -> None:
    op.create_table(
        TABLE,
        sa.Column("target_id", sa.String(20), primary_key=True),
        sa.Column("fiscal_year", sa.String(4), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("bd_owner_id", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_amount_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.Column(
            "revision_of", sa.String(20), sa.ForeignKey("sales_targets.target_id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("revision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.CheckConstraint("fiscal_year ~ '^FY[0-9]{2}$'", name="ck_sales_targets_fiscal_year_format"),
        sa.CheckConstraint("extract(day from period_month) = 1", name="ck_sales_targets_period_month_first"),
        sa.CheckConstraint("target_amount_usd >= 0", name="ck_sales_targets_amount_not_negative"),
        sa.CheckConstraint("currency = 'USD'", name="ck_sales_targets_currency_usd"),
        sa.CheckConstraint("status IN ('DRAFT', 'LOCKED', 'SUPERSEDED')", name="ck_sales_targets_status"),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND locked_at IS NULL AND locked_by IS NULL)"
            " OR (status <> 'DRAFT' AND locked_at IS NOT NULL AND locked_by IS NOT NULL)",
            name="ck_sales_targets_lock_stamped",
        ),
        sa.CheckConstraint(
            "revision_of IS NULL OR length(btrim(coalesce(revision_note, ''))) > 0",
            name="ck_sales_targets_revision_noted",
        ),
    )
    op.create_index(
        "uq_sales_targets_current",
        TABLE,
        ["fiscal_year", "period_month", "bd_owner_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'SUPERSEDED'"),
    )
    op.create_index(
        "uq_sales_targets_revision_of",
        TABLE,
        ["revision_of"],
        unique=True,
        postgresql_where=sa.text("revision_of IS NOT NULL"),
    )
    op.create_index("ix_sales_targets_fiscal_year_month", TABLE, ["fiscal_year", "period_month"])
    op.create_index("ix_sales_targets_owner_month", TABLE, ["bd_owner_id", "period_month"])


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        count = conn.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()
        if count:
            raise RuntimeError(f"0040 stopped: {TABLE} already exists and holds {count} row(s)")
        # Built by create_all, without the trigger. Empty, so rebuild it here.
        op.drop_table(TABLE)
    _create_table()
    op.execute(GUARD_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_sales_targets_guard BEFORE INSERT OR UPDATE OR DELETE ON sales_targets "
        "FOR EACH ROW EXECUTE FUNCTION sales_targets_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sales_targets_guard ON sales_targets")
    op.execute("DROP FUNCTION IF EXISTS sales_targets_guard()")
    op.drop_index("ix_sales_targets_owner_month", table_name=TABLE)
    op.drop_index("ix_sales_targets_fiscal_year_month", table_name=TABLE)
    op.drop_index("uq_sales_targets_revision_of", table_name=TABLE)
    op.drop_index("uq_sales_targets_current", table_name=TABLE)
    op.drop_table(TABLE)

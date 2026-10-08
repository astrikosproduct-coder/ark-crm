"""Pipeline snapshots: the open pipeline as it stood on a day, written at month-end

Revision ID: 0041_pipeline_snapshots
Revises: 0040_sales_targets
Create Date: 2026-09-28

Dashboard Phase 1 (28 Sep 2026). A pursuit that is won or lost leaves the
pipeline, so last month's pipeline cannot be rebuilt from live rows. It has to
be written down on the day. No column is added to any existing table.

WHO WRITES IT
    app/pipeline_snapshots.py: a timer inside the API at 23:55 company time on
    the last day of each month, and POST /api/pipeline-snapshots by hand. The
    timer is the one exception to CLAUDE.md hard rule 6 (decided 28 Sep 2026):
    it writes aggregates and nothing else, and changes no record.

ONE DIMENSION PER ROW
    One ALL row, then one row per BD Owner, per Booking Region, per Segment.
    Never crossed. `dimension` says which, which is the one deviation from the
    brief: without it, NULL would have to mean both "all regions" (the ALL row)
    and "no region recorded" (a Booking Region row), and the two would collide
    on the unique index.

NO DUPLICATES
    `uq_pipeline_snapshots_slice` is UNIQUE NULLS NOT DISTINCT (PostgreSQL 15+),
    so two ALL rows for one day collide even though every dimension column is
    NULL. A second run for the same day inserts nothing.

INSERT-ONLY
    `trg_pipeline_snapshots_insert_only` refuses every UPDATE. DELETE is left to
    a person at psql, to remove a mistaken run.

PRE-CREATED TABLE
    As 0040: a table create_all built early is rebuilt if empty. The writer
    refuses to run until this trigger exists, so it cannot have filled one.

DEPLOY ORDER
    alembic upgrade head
    (start the API — its first start writes today's snapshot, the chart's
     starting point, because the table is empty)

DOWNGRADE drops the table and every snapshot in it. They cannot be rebuilt.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_pipeline_snapshots"
down_revision = "0040_sales_targets"
branch_labels = None
depends_on = None

TABLE = "pipeline_snapshots"


def _create_table() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("bd_owner_id", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("booking_region", sa.String(40), nullable=True),
        sa.Column("segment", sa.String(40), nullable=True),
        sa.Column("open_value_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("weighted_value_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("deal_count", sa.Integer(), nullable=False),
        sa.Column("unpriced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.CheckConstraint(
            "dimension IN ('ALL', 'BD_OWNER', 'BOOKING_REGION', 'SEGMENT')", name="ck_pipeline_snapshots_dimension"
        ),
        sa.CheckConstraint(
            "(dimension = 'ALL' AND bd_owner_id IS NULL AND booking_region IS NULL AND segment IS NULL)"
            " OR (dimension = 'BD_OWNER' AND booking_region IS NULL AND segment IS NULL)"
            " OR (dimension = 'BOOKING_REGION' AND bd_owner_id IS NULL AND segment IS NULL)"
            " OR (dimension = 'SEGMENT' AND bd_owner_id IS NULL AND booking_region IS NULL)",
            name="ck_pipeline_snapshots_one_dimension",
        ),
        sa.CheckConstraint(
            "deal_count >= 0 AND unpriced_count >= 0 AND unpriced_count <= deal_count",
            name="ck_pipeline_snapshots_counts",
        ),
    )
    op.create_index(
        "uq_pipeline_snapshots_slice",
        TABLE,
        ["snapshot_date", "dimension", "bd_owner_id", "booking_region", "segment"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        count = conn.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()
        if count:
            raise RuntimeError(f"0041 stopped: {TABLE} already exists and holds {count} row(s)")
        op.drop_table(TABLE)
    _create_table()
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pipeline_snapshots_insert_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'pipeline snapshot % is history: snapshots are never updated', OLD.id
                USING ERRCODE = 'check_violation';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_pipeline_snapshots_insert_only BEFORE UPDATE ON pipeline_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION pipeline_snapshots_insert_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pipeline_snapshots_insert_only ON pipeline_snapshots")
    op.execute("DROP FUNCTION IF EXISTS pipeline_snapshots_insert_only()")
    op.drop_index("uq_pipeline_snapshots_slice", table_name=TABLE)
    op.drop_table(TABLE)

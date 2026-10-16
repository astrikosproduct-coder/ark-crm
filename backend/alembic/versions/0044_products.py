"""Products: the catalogue and its price matrix become tables

Revision ID: 0044_products
Revises: 0041_pipeline_snapshots
Create Date: 2026-10-12

Products, step 1 (12 Oct 2026). The catalogue was a file bundled into the
browser (spec/seed/products.json, prices.json), so the server could not check a
product a Lead named, and the four fields that were meant to pick one — S!aP
Solution Suite, Suite Demonstrated, Secondary S!aP Suites on a Lead, Expansion
Suites on a Deal — were typed by hand from 3 Sep 2026.

TWO TABLES, AND ONLY THESE
    products         one row per catalogue item — the register's CATALOGUE ITEM
                     section, column for column.
    product_prices   one row per item and deployment size — PRICE MATRIX.
    Sizes, regions and FX, pricing parameters, the rate card and support tiers
    stay bundled: only Quotes reads them, and no table is made for a module
    that is not built (CLAUDE.md rule 1).

NOTHING IS FILLED HERE
    load_price_book.py reads the price book file and fills both tables. A
    migration that read a file from the frontend's folder would fail wherever
    the two are not deployed side by side.

WHAT THE FILE DOES NOT SAY IS LEFT EMPTY
    supports_perpetual, has_annual_updates_option, quantity_allowed,
    unit_of_measure and the effective dates are nullable: the price book states
    none of them, and an unticked box would claim "no" where nobody has
    answered. product_prices.size is NULL for an item with one price at every
    size (the user packs); price_book_version is NULL until an edition is named.

NO COLUMN IS ADDED TO leads OR deals
    The four picker fields keep their columns. A picked product is stored as
    its product_id; what was typed before stays as typed until someone picks —
    see app/products.py and products_typed_suites.py.

PRE-CREATED TABLE
    As 0040 and 0041: a table create_all built early is rebuilt if it is empty.

DEPLOY ORDER
    alembic upgrade head
    python load_price_book.py            (dry run, then --apply)
    python products_step1_metadata.py    (dry run, then --apply)
    python products_typed_suites.py      (report, then --apply)

DOWNGRADE drops both tables. The Leads and Deals columns are untouched, so a
picked product would read as its product_id afterwards.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_products"
down_revision = "0041_pipeline_snapshots"
branch_labels = None
depends_on = None

TABLES = ("product_prices", "products")


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in TABLES:
        if inspector.has_table(table):
            count = conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
            if count:
                raise RuntimeError(f"0044 stopped: {table} already exists and holds {count} row(s)")
            op.drop_table(table)

    op.create_table(
        "products",
        sa.Column("product_id", sa.String(20), primary_key=True),
        sa.Column("sku_code", sa.String(30), nullable=False),
        sa.Column("item_name", sa.String(150), nullable=False),
        sa.Column("catalogue_category", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("charge_type", sa.String(40), nullable=True),
        sa.Column("pricing_basis", sa.String(40), nullable=True),
        sa.Column("supports_perpetual", sa.Boolean(), nullable=True),
        sa.Column("has_annual_updates_option", sa.Boolean(), nullable=True),
        sa.Column("quantity_allowed", sa.Boolean(), nullable=True),
        sa.Column("unit_of_measure", sa.String(40), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint("sku_code", name="uq_products_sku_code"),
    )
    op.create_index("ix_products_catalogue_category", "products", ["catalogue_category"])

    op.create_table(
        "product_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.String(20),
            sa.ForeignKey("products.product_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("list_price_usa_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("price_book_version", sa.String(20), nullable=True),
        sa.CheckConstraint("list_price_usa_usd >= 0", name="ck_product_prices_not_negative"),
    )
    # One price per item, size and edition. NULLS NOT DISTINCT (PostgreSQL 15+),
    # so an item with one price at every size cannot be given two.
    op.create_index(
        "uq_product_prices_item_size_version",
        "product_prices",
        ["product_id", "size", "price_book_version"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_product_prices_item_size_version", table_name="product_prices")
    op.drop_table("product_prices")
    op.drop_index("ix_products_catalogue_category", table_name="products")
    op.drop_table("products")

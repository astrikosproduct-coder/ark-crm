"""Price Books: books, editions, prices, and the sizing guide

Revision ID: 0045_price_books
Revises: 0044_products
Create Date: 2026-10-13

Products, phase 3 (13 Oct 2026). Step 1 gave a product a list price per size in
`product_prices`: one price list, in USA USD, filled from a file. This turns it
into Zoho's Price Books, editable in the app:

  price_books          one row per book. Exactly one is the STANDARD book (the
                       master, USA USD); the others are regional, and each
                       carries what the price book file's "Region & FX" row
                       held — its currency, region pricing % and FX rate. A
                       regional price is the Standard price x the two, unless
                       the book holds a price of its own for that product.
  price_book_editions  the price list as it stood: Draft (edited), Current
                       (what is sold from), Retired (kept, for what was quoted
                       from it). One Current at a time. An edition covers every
                       book.
  price_book_entries   one price: a product, at a size or at none, in one book
                       and one edition. Replaces `product_prices`. A Support
                       product holds a percentage of the licence instead of a
                       price.
  deployment_sizes     the T-shirt sizes as records — CPQ's Sizing Guide — where
                       they were two dropdown lists. A price names its size by
                       `size_id`.

WHAT HAPPENS TO THE PRICES ALREADY THERE
    Every `product_prices` row moves into the Standard book, in a first edition
    marked Current, at the same amount. The sizes those rows name become
    `deployment_sizes` rows, named as the Size dropdown labelled them ("XS",
    "Unlimited"), in its order. Nothing is re-priced. `product_prices` is then
    dropped.

    An empty `product_prices` (a server that has not loaded the price book yet)
    makes no book and no edition: load_price_book.py creates them.

DEPLOY ORDER: dump -> alembic upgrade head -> products_phase3_metadata.py
--apply (the loader reads choices it adds) -> load_price_book.py --apply ->
start the new code. See DEPLOY.md.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045_price_books"
down_revision = "0044_products"
branch_labels = None
depends_on = None

# Dropped in this order if app/main.py's create_all made them first, empty.
NEW_TABLES = ("price_book_entries", "price_books", "price_book_editions", "deployment_sizes")

STANDARD_ID = "PB-0001"
#: The price book file's own name for the master price list.
STANDARD_NAME = "USA USD"
FIRST_EDITION_ID = "PBE-0001"
FIRST_EDITION_NAME = "Edition 1"
SIZE_PICKLIST = "products__size"


def _custom_fields() -> sa.Column:
    return sa.Column("custom_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # New code started before this migration leaves these behind, EMPTY
    # (create_all). Empty, they are dropped and made properly; holding rows,
    # the migration stops rather than guess.
    for table in NEW_TABLES:
        if inspector.has_table(table):
            count = conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
            if count:
                raise RuntimeError(f"0045 stopped: {table} already exists and holds {count} row(s)")
            op.drop_table(table)

    op.create_table(
        "price_books",
        sa.Column("price_book_id", sa.String(20), primary_key=True),
        sa.Column("price_book_name", sa.String(120), nullable=False),
        sa.Column("is_standard", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("currency", sa.String(10), nullable=True),
        # Fractions, as every percent in ARK: 1 is 100%, 0.56 is 56%.
        sa.Column("region_pricing_pct", sa.Numeric(9, 6), nullable=True),
        sa.Column("fx_rate_local_per_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("display_format", sa.String(80), nullable=True),
        sa.Column("rate_effective_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_stamps(),
        _custom_fields(),
        sa.UniqueConstraint("price_book_name", name="uq_price_books_name"),
        sa.CheckConstraint("region_pricing_pct IS NULL OR region_pricing_pct >= 0", name="ck_price_books_pct"),
        sa.CheckConstraint("fx_rate_local_per_usd IS NULL OR fx_rate_local_per_usd > 0", name="ck_price_books_fx"),
    )
    op.create_index(
        "uq_price_books_one_standard",
        "price_books",
        ["is_standard"],
        unique=True,
        postgresql_where=sa.text("is_standard"),
    )

    op.create_table(
        "price_book_editions",
        sa.Column("edition_id", sa.String(20), primary_key=True),
        # The register's name for it, on every price row until now.
        sa.Column("price_book_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("made_current_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        _custom_fields(),
        sa.UniqueConstraint("price_book_version", name="uq_price_book_editions_name"),
        sa.CheckConstraint("status IN ('DRAFT', 'CURRENT', 'RETIRED')", name="ck_price_book_editions_status"),
    )
    op.create_index(
        "uq_price_book_editions_one_current",
        "price_book_editions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'CURRENT'"),
    )

    op.create_table(
        "deployment_sizes",
        sa.Column("size_id", sa.String(20), primary_key=True),
        sa.Column("size_code", sa.String(20), nullable=False),
        sa.Column("managed_assets_cap", sa.String(30), nullable=True),
        sa.Column("typical_deployment", sa.String(200), nullable=True),
        sa.Column("subsystem_types", sa.String(20), nullable=True),
        sa.Column("base_users_included", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_stamps(),
        _custom_fields(),
        sa.UniqueConstraint("size_code", name="uq_deployment_sizes_code"),
    )

    op.create_table(
        "price_book_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "price_book_id", sa.String(20), sa.ForeignKey("price_books.price_book_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "edition_id", sa.String(20), sa.ForeignKey("price_book_editions.edition_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("product_id", sa.String(20), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        # NULL: one price whatever the size (a user pack, a day rate).
        sa.Column("size_id", sa.String(20), sa.ForeignKey("deployment_sizes.size_id", ondelete="RESTRICT"), nullable=True),
        # In the BOOK's currency: USD in the Standard book, local in a regional one.
        sa.Column("list_price", sa.Numeric(18, 2), nullable=True),
        # A Support product's price: a fraction of the licence value.
        sa.Column("pct_of_annual_licence", sa.Numeric(9, 6), nullable=True),
        *_stamps(),
        sa.CheckConstraint(
            "(list_price IS NULL) <> (pct_of_annual_licence IS NULL)", name="ck_price_book_entries_one_value"
        ),
        sa.CheckConstraint("list_price IS NULL OR list_price >= 0", name="ck_price_book_entries_price"),
        sa.CheckConstraint(
            "pct_of_annual_licence IS NULL OR pct_of_annual_licence >= 0", name="ck_price_book_entries_pct"
        ),
    )
    op.create_index(
        "uq_price_book_entries_cell",
        "price_book_entries",
        ["price_book_id", "edition_id", "product_id", "size_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_price_book_entries_product", "price_book_entries", ["product_id"])
    op.create_index("ix_price_book_entries_edition", "price_book_entries", ["edition_id"])

    if not inspector.has_table("product_prices"):
        return

    held = conn.execute(sa.text("SELECT count(*) FROM product_prices")).scalar()
    if held:
        versions = conn.execute(
            sa.text("SELECT DISTINCT price_book_version FROM product_prices WHERE price_book_version IS NOT NULL")
        ).scalars().all()
        if versions:
            raise RuntimeError(
                f"0045 stopped: product_prices names price book versions {versions}. The first load carried none; "
                "decide which edition each belongs to before moving them."
            )
        today = date.today()
        conn.execute(
            sa.text(
                "INSERT INTO price_books (price_book_id, price_book_name, is_standard, currency, region_pricing_pct,"
                " fx_rate_local_per_usd, active) VALUES (:id, :name, true, 'USD', 1, 1, true)"
            ),
            {"id": STANDARD_ID, "name": STANDARD_NAME},
        )
        conn.execute(
            sa.text(
                "INSERT INTO price_book_editions (edition_id, price_book_version, status, effective_from, made_current_at)"
                " VALUES (:id, :name, 'CURRENT', :today, :now)"
            ),
            {"id": FIRST_EDITION_ID, "name": FIRST_EDITION_NAME, "today": today, "now": datetime.now(timezone.utc)},
        )

        # The sizes the prices name, as the Size dropdown labelled and ordered them.
        choices = {
            row.key: (row.label, row.sort_order)
            for row in conn.execute(
                sa.text("SELECT key, label, sort_order FROM picklist_values WHERE picklist_key = :p"), {"p": SIZE_PICKLIST}
            )
        }
        named = conn.execute(sa.text("SELECT DISTINCT size FROM product_prices WHERE size IS NOT NULL")).scalars().all()
        named.sort(key=lambda key: (choices.get(key, (key, 999))[1], key))
        for number, key in enumerate(named, start=1):
            label, order = choices.get(key, (key, number))
            size_id = f"SZ-{number:04d}"
            conn.execute(
                sa.text(
                    "INSERT INTO deployment_sizes (size_id, size_code, sort_order, active) VALUES (:id, :code, :sort, true)"
                ),
                {"id": size_id, "code": label, "sort": order},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO price_book_entries (price_book_id, edition_id, product_id, size_id, list_price)"
                    " SELECT :book, :edition, product_id, :size_id, list_price_usa_usd FROM product_prices WHERE size = :key"
                ),
                {"book": STANDARD_ID, "edition": FIRST_EDITION_ID, "size_id": size_id, "key": key},
            )
        conn.execute(
            sa.text(
                "INSERT INTO price_book_entries (price_book_id, edition_id, product_id, size_id, list_price)"
                " SELECT :book, :edition, product_id, NULL, list_price_usa_usd FROM product_prices WHERE size IS NULL"
            ),
            {"book": STANDARD_ID, "edition": FIRST_EDITION_ID},
        )
        moved = conn.execute(sa.text("SELECT count(*) FROM price_book_entries")).scalar()
        if moved != held:
            raise RuntimeError(f"0045 stopped: {held} prices to move, {moved} moved")

        # The id counters start past what was just numbered by hand (app/ids.py).
        for name, prefix, last in (
            ("price_books", "PB", 1),
            ("price_book_editions", "PBE", 1),
            ("deployment_sizes", "SZ", len(named)),
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO id_sequences (name, prefix, pad, last_value) VALUES (:name, :prefix, 4, :last)"
                    " ON CONFLICT (name) DO UPDATE SET last_value = GREATEST(id_sequences.last_value, EXCLUDED.last_value)"
                ),
                {"name": name, "prefix": prefix, "last": last},
            )

    op.drop_table("product_prices")


def downgrade() -> None:
    """Back to one price list. Only the Standard book's CURRENT edition can go back."""
    conn = op.get_bind()
    op.create_table(
        "product_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(20), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("list_price_usa_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("price_book_version", sa.String(20), nullable=True),
        sa.CheckConstraint("list_price_usa_usd >= 0", name="ck_product_prices_not_negative"),
    )
    op.create_index(
        "uq_product_prices_item_size_version",
        "product_prices",
        ["product_id", "size", "price_book_version"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    conn.execute(
        sa.text(
            "INSERT INTO product_prices (product_id, size, list_price_usa_usd)"
            " SELECT e.product_id, upper(s.size_code), e.list_price FROM price_book_entries e"
            " JOIN price_books b ON b.price_book_id = e.price_book_id AND b.is_standard"
            " JOIN price_book_editions ed ON ed.edition_id = e.edition_id AND ed.status = 'CURRENT'"
            " LEFT JOIN deployment_sizes s ON s.size_id = e.size_id"
            " WHERE e.list_price IS NOT NULL"
        )
    )
    op.drop_table("price_book_entries")
    op.drop_table("deployment_sizes")
    op.drop_table("price_book_editions")
    op.drop_table("price_books")
    conn.execute(sa.text("DELETE FROM id_sequences WHERE name IN ('price_books', 'price_book_editions', 'deployment_sizes')"))

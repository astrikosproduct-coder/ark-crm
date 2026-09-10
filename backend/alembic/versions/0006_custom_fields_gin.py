"""GIN indexes on custom_fields

Revision ID: 0006_cf_gin
Revises: 0005_opportunities
Create Date: 2026-09-04

A GIN index on every custom_fields column, so that filtering CRM records by an
Administration-created field can use an index instead of reading the table.

WHY jsonb_path_ops AND NOT THE DEFAULT
---------------------------------------
Chosen from the query pattern that actually exists, not from what JSONB can do
in general.

The list endpoints take equality filters as query parameters —
`?account_type=PARTNER_SI` — and apply them today by fetching the rows and
comparing in Python (`_matches` in routers/accounts.py). There is not one SQL
JSONB operator anywhere in app/ right now. When that filter moves into SQL at
cutover, an equality test against a custom field is a CONTAINMENT query:

    WHERE custom_fields @> '{"customer_priority_cf": "High"}'

`jsonb_path_ops` indexes exactly that operator. It is roughly half the size of
the default `jsonb_ops` and faster for containment, because it stores a hash per
path rather than an entry per key AND per value.

What it gives up is the key-existence family — `?`, `?|`, `?&`. Nothing in this
application uses them: no endpoint asks "which records have this custom field
set at all". Indexing for that would be indexing for a requirement nobody has.
If one appears, an additional default-ops index is a one-line migration.

WHAT THIS DOES NOT CHANGE
--------------------------
Nothing observable. An index changes how PostgreSQL finds rows, never what it
returns, and no application code is touched by this migration.

ROUND 5
-------
products, quotes, quote_items, poc and bid_gates do not exist yet. When they are
created they take `custom_fields` and this same index in their own CREATE TABLE
migration — see the note in app/models.py, so it is part of the table's
definition rather than a manual step somebody has to remember afterwards.
"""

from typing import Sequence, Union

from alembic import op

revision: str = '0006_cf_gin'
down_revision: Union[str, Sequence[str], None] = '0005_opportunities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("accounts", "contacts", "leads", "opportunities", "deals")


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"CREATE INDEX ix_{table}_custom_fields_gin "
            f"ON {table} USING gin (custom_fields jsonb_path_ops)"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_custom_fields_gin")

"""Round 6: picklists.sort_order

Revision ID: 0003_picklist_sort
Revises: 0002_round6
Create Date: 2026-09-03

Give picklists an explicit order, so regenerating picklists.json does not
reshuffle it.

A JSON object's key order is meaningless to the frontend — every read is
picklists[key] — so this column exists for the git diff, not for the reader.
Without it the file comes back alphabetised, which moves all 107 picklists and
rewrites 2,754 lines the first time anybody publishes, hiding the single label
that actually changed inside a diff nobody can review.

THE BACKFILL RECOVERS THE REGISTER'S OWN ORDER
-----------------------------------------------
picklist_values.id is a serial, and the bootstrap inserted the values in the
order picklists.json declares them. So the lowest value id per picklist ranks
the picklists in file order, exactly, and no order has to be guessed or
re-derived from the workbook.

A picklist with no values sorts last (there are none today; the coalesce is
there so this cannot fail on a database where somebody has since made one).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_picklist_sort'
down_revision: Union[str, Sequence[str], None] = '0002_round6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "picklists",
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    )

    op.execute(
        """
        UPDATE picklists AS p
           SET sort_order = ranked.position
          FROM (
                SELECT picklist_key,
                       ROW_NUMBER() OVER (ORDER BY first_value_id, picklist_key)
                           AS position
                  FROM (
                        SELECT pl.picklist_key,
                               COALESCE(MIN(pv.id), 2147483647) AS first_value_id
                          FROM picklists pl
                          LEFT JOIN picklist_values pv
                                 ON pv.picklist_key = pl.picklist_key
                         GROUP BY pl.picklist_key
                       ) AS firsts
               ) AS ranked
         WHERE ranked.picklist_key = p.picklist_key
        """
    )


def downgrade() -> None:
    op.drop_column("picklists", "sort_order")

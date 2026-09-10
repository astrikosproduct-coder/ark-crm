"""Field anchors: position becomes a property of the placement

Revision ID: 0013_anchors
Revises: 0012_employee_id
Create Date: 2026-09-10

THE PROBLEM THIS FIXES
----------------------
Until now a placement's position was its `section_id` plus its `sort_order`,
and `section` was doing two jobs at once: saying what KIND of field this is
(CROSS-CUTTING, SYSTEM, RECORD STATE) and saying where it draws. Those are the
same value today, which is why On Hold Reason sits at order 74 in CROSS-CUTTING
while the Lead Status that triggers it sits at order 19 in STAGE 0 — CONNECT:
fifty-five fields and one tab away from the question it answers.

A conditional field that is not in the same form as its trigger physically
cannot react before a save. The user sets the status, saves, the page
re-renders, and only then is a second box offered on a second surface. Two
saves for one answer.

WHAT AN ANCHOR IS
-----------------
`anchor_field` names another field ON THE SAME MODULE next to which this
placement draws. `section_id` keeps saying what kind of field it is;
`anchor_field` says where it goes. They are allowed to disagree, and the whole
point is that they do — On Hold Reason stays a CROSS-CUTTING field and renders
beneath Lead Status wherever Lead Status happens to be.

    anchor_field      an api_name on this module, or NULL for "draw me in my
                      own section's list, in sort_order" — the old behaviour,
                      which is what every row still has after this migration
    anchor_position   'after'  a new row directly below the anchor
                      'beside' the adjacent grid cell
    layout_span       'full' | 'half' | NULL. NULL means "whatever this field
                      type would take on its own", which is what every existing
                      row gets, so nothing moves.

NOTHING MOVES HERE. All three columns land NULL on all 674 placements. This
migration adds the vocabulary; 0013 does not use it. Anchoring the six reason
placements is a data change made through Administration, not schema.

WHY THERE IS NO FOREIGN KEY ON anchor_field
--------------------------------------------
The obvious FK is (module_key, scope_key, anchor_field) -> the columns of
uq_field_placements_qname, and it would be correct. It is not here for one
reason: it is self-referential, and rebuild_metadata.py empties this table with
a single bulk `DELETE FROM field_placements`. Postgres checks a non-deferrable
FK per row as the statement runs, so that delete would fail against itself the
moment any row anchored to any other. Making it DEFERRABLE to work around that
buys integrity in one place at the cost of a constraint that silently does not
hold until COMMIT, which is worse to reason about than the API check.

So: the two things a CHECK can say are said here, and the two it cannot —
"the anchor exists and is active on this module" and "the anchor chain does not
loop" — are enforced in app/routers/metadata.py where the anchor is set. A
dangling anchor is treated as no anchor by the resolver rather than as an
error: a field that draws in its own section is a worse screen, not a broken
one.
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_anchors"
down_revision = "0012_employee_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "field_placements", sa.Column("anchor_field", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "field_placements", sa.Column("anchor_position", sa.String(length=10), nullable=True)
    )
    op.add_column(
        "field_placements", sa.Column("layout_span", sa.String(length=10), nullable=True)
    )

    # An anchor with no position, or a position anchored to nothing, is half a
    # placement decision. Both or neither.
    op.create_check_constraint(
        "ck_field_placements_anchor_pair",
        "field_placements",
        "(anchor_field IS NULL) = (anchor_position IS NULL)",
    )
    op.create_check_constraint(
        "ck_field_placements_anchor_position",
        "field_placements",
        "anchor_position IS NULL OR anchor_position IN ('after', 'beside')",
    )
    # The one cycle a CHECK can see. Longer loops need the walk in the router.
    op.create_check_constraint(
        "ck_field_placements_anchor_self",
        "field_placements",
        "anchor_field IS NULL OR anchor_field <> api_name",
    )
    op.create_check_constraint(
        "ck_field_placements_layout_span",
        "field_placements",
        "layout_span IS NULL OR layout_span IN ('full', 'half')",
    )

    # "What is anchored to this field on this module" — asked once per section
    # the form builder walks, and by the delete guard before it takes an anchor
    # away from the fields hanging off it. Partial: anchors are a handful of
    # rows out of hundreds, so an index over the whole column would be ignored.
    op.create_index(
        "ix_field_placements_anchor",
        "field_placements",
        ["module_key", "anchor_field"],
        postgresql_where=sa.text("anchor_field IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_field_placements_anchor", table_name="field_placements")
    op.drop_constraint("ck_field_placements_layout_span", "field_placements")
    op.drop_constraint("ck_field_placements_anchor_self", "field_placements")
    op.drop_constraint("ck_field_placements_anchor_position", "field_placements")
    op.drop_constraint("ck_field_placements_anchor_pair", "field_placements")
    op.drop_column("field_placements", "layout_span")
    op.drop_column("field_placements", "anchor_position")
    op.drop_column("field_placements", "anchor_field")

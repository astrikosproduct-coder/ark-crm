"""Feedback from any signed-in user, read by Developers only; Developer joins the roles picklist

Revision ID: 0032_feedback
Revises: 0031_deal_stage_move_reasons
Create Date: 2026-09-17

UX roadmap item 2 (17 Sep 2026). A message icon in the top bar lets anyone with
a role leave feedback — a category, a message, and the page they were on. Only
the DEVELOPER role can read it, and that is enforced on the server
(app/auth.py::require_developer), never by hiding a screen.

THREE THINGS

1. `feedback` — one row per message. `created_by` / `created_at` are stamped
   by the server (CLAUDE.md: identity is never taken from a request body).
   `page_path` / `record_ref` are captured by the page, so a developer sees
   where the person was without asking. No attachment column: file upload stays
   out of scope (decided 17 Sep 2026).

2. Two picklists, `feedback__category` and `feedback__status`, so neither
   dropdown is hardcoded (CLAUDE.md hard rule 4) and an administrator can rename
   a category in Administration like any other.

3. DEVELOPER in `administration__roles`. The role row has been seeded since
   the dev-tools gate (seed.py), but the picklist that is meant to share its
   vocabulary never got the key — hard rule 4 says the two agree. The role
   row is inserted here too, so a database built only from migrations has it.

DEPLOY ORDER

    alembic upgrade head
    python regenerate_spec.py --apply      # picklists.json gains the three picklists' values
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_feedback"
down_revision = "0031_deal_stage_move_reasons"
branch_labels = None
depends_on = None

CATEGORIES = [("BUG", "Something is broken"), ("IDEA", "Idea or request"), ("CONFUSING", "Confusing"), ("OTHER", "Other")]
STATUSES = [("NEW", "New"), ("READ", "Read"), ("DONE", "Done")]


def _picklist(key: str, label: str, values: list[tuple[str, str]]) -> None:
    op.execute(
        sa.text(
            "INSERT INTO picklists (picklist_key, label, sort_order, active, created_at, updated_at) "
            "SELECT :key, :label, COALESCE((SELECT MAX(sort_order) FROM picklists), 0) + 1, true, now(), now() "
            "WHERE NOT EXISTS (SELECT 1 FROM picklists WHERE picklist_key = :key)"
        ).bindparams(key=key, label=label)
    )
    for sort, (value, value_label) in enumerate(values, start=1):
        op.execute(
            sa.text(
                "INSERT INTO picklist_values (picklist_key, key, label, sort_order, active, created_at, updated_at) "
                "SELECT :key, :value, :label, :sort, true, now(), now() "
                "WHERE NOT EXISTS (SELECT 1 FROM picklist_values WHERE picklist_key = :key AND key = :value)"
            ).bindparams(key=key, value=value, label=value_label, sort=sort)
        )


def _create_feedback() -> None:
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(20), primary_key=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page_path", sa.String(500), nullable=True),
        sa.Column("record_ref", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("created_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_by", sa.String(20), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(message)) > 0", name="ck_feedback_message_not_blank"),
    )
    op.create_index("ix_feedback_status", "feedback", ["status"])
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"])


def upgrade() -> None:
    conn = op.get_bind()
    # app/main.py runs Base.metadata.create_all on startup, so a dev server that
    # reloaded after models.py gained Feedback has already created this table —
    # empty, with exactly the model's shape. Accepted (as 0020 does for
    # pursuit_groups); a table already holding rows is something else, and stops.
    if sa.inspect(conn).has_table("feedback"):
        count = conn.execute(sa.text("SELECT count(*) FROM feedback")).scalar()
        if count:
            raise RuntimeError(f"0032 stopped: feedback already exists and holds {count} row(s)")
    else:
        _create_feedback()

    _picklist("feedback__category", "Feedback category", CATEGORIES)
    _picklist("feedback__status", "Feedback status", STATUSES)

    op.execute(
        "INSERT INTO roles (role_id, name, description, sort_order, active, created_at, updated_at) "
        "SELECT 'DEVELOPER', 'Developer', 'For development and testing only. Reads user feedback.', "
        "       COALESCE((SELECT MAX(sort_order) FROM roles), 0) + 1, true, now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE role_id = 'DEVELOPER')"
    )
    op.execute(
        "INSERT INTO picklist_values (picklist_key, key, label, sort_order, active, created_at, updated_at) "
        "SELECT 'administration__roles', 'DEVELOPER', 'Developer', COALESCE(MAX(sort_order), 0) + 1, true, now(), now() "
        "  FROM picklist_values WHERE picklist_key = 'administration__roles' "
        "HAVING NOT EXISTS (SELECT 1 FROM picklist_values "
        "                   WHERE picklist_key = 'administration__roles' AND key = 'DEVELOPER')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM picklist_values WHERE picklist_key = 'administration__roles' AND key = 'DEVELOPER'")
    op.execute("DELETE FROM picklists WHERE picklist_key IN ('feedback__category', 'feedback__status')")
    op.drop_index("ix_feedback_created_at", table_name="feedback")
    op.drop_index("ix_feedback_status", table_name="feedback")
    op.drop_table("feedback")

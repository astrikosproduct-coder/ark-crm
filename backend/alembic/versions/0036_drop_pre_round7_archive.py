"""Retire the pre-Round-7 archive of the field register

Revision ID: 0036_drop_pre_round7_archive
Revises: 0035_lead_pilot_po_received_date
Create Date: 2026-09-21

Migration 0008 copied field_metadata into field_metadata_pre_round7 before
fields gained placements, so a version published before then could still be
explained. Version 1 goes live with no earlier history (decided 21 Sep 2026:
"a fresh new application"), and fresh_start_register.py collapses the
published versions into one — nothing left refers to the archive.

The downgrade recreates the table EMPTY, with field_metadata's columns: the
archived rows are not recoverable from here. They are in git history's
database dumps only if someone kept one.
"""

from __future__ import annotations

from alembic import op

revision = "0036_drop_pre_round7_archive"
down_revision = "0035_lead_pilot_po_received_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS field_metadata_pre_round7")


def downgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS field_metadata_pre_round7 (LIKE field_metadata INCLUDING ALL)")

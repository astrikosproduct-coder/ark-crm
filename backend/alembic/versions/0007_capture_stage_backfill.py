"""Backfill capture_stage on pipeline fields in numbered stage sections

Revision ID: 0007_capture_stage
Revises: 0006_cf_gin
Create Date: 2026-09-04

Repairs fields that sit in a `STAGE n — …` section of a pipeline module but
carry no capture_stage, which makes them render on no screen at all.

THE DEFECT
----------
capture_stage is a REGISTER COLUMN on field_metadata, not a field of its own. It
decides two things in the frontend:

  * which stage tab shows the field — sectionsForStage() matches
    `capture_stage === stage` (src/lib/pipeline.ts)
  * whether the Details tab shows it — that tab deliberately excludes every
    section whose name starts with STAGE (PipelineRecordPage.tsx)

A field in a numbered STAGE section with capture_stage NULL therefore satisfies
neither and is invisible everywhere, while looking perfectly correct in
Administration. Two such fields exist, both created through the Round-6
Administration UI, which offered capture_stage as an optional box and defaulted
it to blank.

THE INVARIANT, VERIFIED BEFORE RELYING ON IT
---------------------------------------------
Across all 133 register rows that sit in a numbered STAGE section, capture_stage
equals the section's own number in every single case — zero exceptions. So the
section number is a sound source for the missing value rather than a guess.

Only NULLs are filled. A row whose capture_stage disagrees with its section is
left exactly as it is and reported by publish validation instead: that would be
a real disagreement about where a field belongs, and this migration has no
business deciding it.

`administration` sections such as "STAGE DEFINITION  (configuration)" are
untouched — they describe stage configuration, they are not pipeline stages, and
their module is not a pipeline module. The `^STAGE [0-9]` pattern excludes them,
which is why it is matched on rather than a bare "STAGE" prefix.
"""

from typing import Sequence, Union

from alembic import op

revision: str = '0007_capture_stage'
down_revision: Union[str, Sequence[str], None] = '0006_cf_gin'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE field_metadata AS f
           SET capture_stage = substring(s.label from '^STAGE ([0-9]+)')::int
          FROM sections AS s,
               modules  AS m
         WHERE s.id = f.section_id
           AND m.module_key = f.module_key
           AND m.is_pipeline
           AND f.capture_stage IS NULL
           AND s.label ~ '^STAGE [0-9]'
        """
    )


def downgrade() -> None:
    # Not reversed. The previous state was "invisible field with a NULL", which
    # is the defect this repaired — restoring it would be restoring a bug, and
    # nothing downstream depends on the NULL being there.
    pass

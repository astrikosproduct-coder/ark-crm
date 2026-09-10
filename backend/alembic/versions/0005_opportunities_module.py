"""Opportunities as a first-class module; pipeline config into PostgreSQL

Revision ID: 0005_opportunities
Revises: 0004_custom_fields
Create Date: 2026-09-04

Makes `opportunities` a real module row, and moves the pipeline structure that
only existed in spec/module_split.json into the metadata tables.

WHAT WAS WRONG
--------------
The register has no `opportunities` sheet. It files every Stage 0-7 pipeline
field under `leads`, and the frontend splits them across Leads, Opportunities
and Deals at load time using spec/module_split.json. So PostgreSQL knew nothing
about Opportunities at all: no module row, no stage ownership, nothing. The
backend's only knowledge was a hardcoded tuple in app/custom_fields.py saying
"opportunities may also take fields from leads" — a fact with no source.

That is the thing that bites at cutover. When /api/opportunities stops being
answered by MSW and starts being answered by FastAPI, the backend has to know
which fields belong to an Opportunity, and it cannot ask a frontend JSON file.

WHAT THIS DOES
--------------
  modules       gains is_pipeline, stage_field, parent_module, parent_link
                and an `opportunities` row
  stages        gains owner_module — which module owns each stage number

Both are columns on the EXISTING generic tables. No opportunity_field_metadata,
no opportunity_stages, no per-module metadata table of any kind.

Stage ownership lands in `stages` because that is where a stage is defined.
`ranges` in module_split.json is then derived (min/max stage per owner) rather
than stored twice.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
It does not create field_metadata rows for Opportunities.

Every Opportunity field is a PROJECTION of a Leads register row — the same
definition, re-homed by capture stage. Materialising them would put a second
row under the same api_name with the same definition, which is the duplicate
metadata this round was told not to create, and it would drift from the
frontend's derivation the first time either changed. The projection rule now
reads its inputs from PostgreSQL (stage ownership, module identity); what it
does not do is store its output.

`stages.applies_to` is left exactly as the register wrote it — still saying
stages 4-7 are 'lead', still wrong, still reported as a register correction on
the Spec Health page. Correcting it here would close a gap the register itself
should close, and nothing reads it: owner_module is what is authoritative now.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0005_opportunities'
down_revision: Union[str, Sequence[str], None] = '0004_custom_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The pipeline, as spec/module_split.json declares it today. Read across into
# the database once, here, so that PostgreSQL becomes the source and the file
# becomes generated output.
#
#   module          stages  stage field      parent          parent link
PIPELINE = [
    ("leads",         (0, 3), "project_stage", None,            None),
    ("opportunities", (4, 6), "project_stage", "leads",         "parent_lead"),
    ("deals",         (7, 9), "deal_stage",    "opportunities", "parent_opportunity"),
]


def upgrade() -> None:
    op.add_column(
        "modules",
        sa.Column("is_pipeline", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("modules", sa.Column("stage_field", sa.String(length=60), nullable=True))
    op.add_column("modules", sa.Column("parent_module", sa.String(length=60), nullable=True))
    op.add_column("modules", sa.Column("parent_link", sa.String(length=120), nullable=True))
    op.create_foreign_key(
        "fk_modules_parent_module", "modules", "modules",
        ["parent_module"], ["module_key"],
    )

    op.add_column("stages", sa.Column("owner_module", sa.String(length=60), nullable=True))
    op.create_foreign_key(
        "fk_stages_owner_module", "stages", "modules",
        ["owner_module"], ["module_key"],
    )

    # `opportunities` as a module row. Ordered directly after leads, which is
    # where it sits in the pipeline and in the application's navigation.
    op.execute(
        """
        INSERT INTO modules (module_key, label, sort_order, active, created_at, updated_at)
        SELECT 'opportunities', 'Opportunities',
               (SELECT sort_order FROM modules WHERE module_key = 'leads'),
               true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM modules WHERE module_key = 'opportunities')
        """
    )
    # Everything that sorted at or after leads shifts down by one to make room,
    # leads itself excluded.
    op.execute(
        """
        UPDATE modules
           SET sort_order = sort_order + 1
         WHERE module_key NOT IN ('leads', 'opportunities')
           AND sort_order >= (SELECT sort_order FROM modules WHERE module_key = 'leads')
        """
    )
    op.execute(
        """
        UPDATE modules
           SET sort_order = (SELECT sort_order FROM modules WHERE module_key = 'leads') + 1
         WHERE module_key = 'opportunities'
        """
    )

    for module_key, (low, high), stage_field, parent, link in PIPELINE:
        op.execute(
            sa.text(
                """
                UPDATE modules
                   SET is_pipeline = true,
                       stage_field = :stage_field,
                       parent_module = :parent,
                       parent_link = :link
                 WHERE module_key = :module_key
                """
            ).bindparams(
                stage_field=stage_field, parent=parent, link=link, module_key=module_key
            )
        )
        op.execute(
            sa.text(
                "UPDATE stages SET owner_module = :module_key "
                " WHERE stage BETWEEN :low AND :high"
            ).bindparams(module_key=module_key, low=low, high=high)
        )


def downgrade() -> None:
    op.drop_constraint("fk_stages_owner_module", "stages", type_="foreignkey")
    op.drop_column("stages", "owner_module")

    op.execute("DELETE FROM modules WHERE module_key = 'opportunities'")

    op.drop_constraint("fk_modules_parent_module", "modules", type_="foreignkey")
    op.drop_column("modules", "parent_link")
    op.drop_column("modules", "parent_module")
    op.drop_column("modules", "stage_field")
    op.drop_column("modules", "is_pipeline")

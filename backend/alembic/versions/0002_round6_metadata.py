"""Round 6: the metadata layer

Revision ID: 0002_round6
Revises: 0001_baseline
Create Date: 2026-09-03

Round 6 — the metadata layer.

Seven tables that hold the field register itself as rows: modules, sections,
field_metadata, picklists, picklist_values, stages and metadata_versions.
See the ROUND 6 section comment in app/models.py for what each one is for and
why deletion here is logical and never a DROP COLUMN.

Nothing in this migration touches a business table. Round 6 defines what a
record may contain; it does not move a single stored value.

After upgrading, populate the tables once from the existing spec files:

    python bootstrap_metadata.py --apply
    python regenerate_spec.py --check
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002_round6'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('modules',
    sa.Column('module_key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('module_key')
    )
    op.create_table('picklists',
    sa.Column('picklist_key', sa.String(length=120), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=True),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('picklist_key')
    )
    op.create_table('metadata_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='published', nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('restored_from', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_by', sa.String(length=20), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['published_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metadata_versions_version_no'), 'metadata_versions', ['version_no'], unique=True)
    op.create_table('picklist_values',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('picklist_key', sa.String(length=120), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['picklist_key'], ['picklists.picklist_key'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('picklist_key', 'key', name='uq_picklist_values_key')
    )
    op.create_index(op.f('ix_picklist_values_picklist_key'), 'picklist_values', ['picklist_key'], unique=False)
    op.create_table('sections',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('module_key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['module_key'], ['modules.module_key'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('module_key', 'label', name='uq_sections_module_label')
    )
    op.create_index(op.f('ix_sections_module_key'), 'sections', ['module_key'], unique=False)
    op.create_table('stages',
    sa.Column('stage', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('prob_min', sa.Integer(), nullable=True),
    sa.Column('prob_max', sa.Integer(), nullable=True),
    sa.Column('owner_role', sa.String(length=30), nullable=True),
    sa.Column('bid_phase', sa.String(length=60), nullable=True),
    sa.Column('applies_to', sa.String(length=20), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_role'], ['roles.role_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('stage')
    )
    op.create_table('field_metadata',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('module_key', sa.String(length=60), nullable=False),
    sa.Column('section_id', sa.Integer(), nullable=False),
    sa.Column('api_name', sa.String(length=120), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('field_type', sa.String(length=30), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('max_length', sa.Integer(), nullable=True),
    sa.Column('picklist_key', sa.String(length=120), nullable=True),
    sa.Column('lookup_target', sa.String(length=60), nullable=True),
    sa.Column('lookup_filter', sa.Text(), nullable=True),
    sa.Column('values_note', sa.Text(), nullable=True),
    sa.Column('capture_stage', sa.Integer(), nullable=True),
    sa.Column('capture_any_stage', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('mandatory_from', sa.Integer(), nullable=True),
    sa.Column('blocks_transition', sa.String(length=40), nullable=True),
    sa.Column('requirement', sa.String(length=20), nullable=False),
    sa.Column('origin', sa.String(length=120), nullable=False),
    sa.Column('source_ref', sa.String(length=120), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('use_case', sa.Text(), nullable=False),
    sa.Column('required_on_skip', sa.Boolean(), nullable=True),
    sa.Column('visibility_condition', sa.Text(), nullable=True),
    sa.Column('condition', sa.Text(), nullable=True),
    sa.Column('computed_formula', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.String(length=20), nullable=True),
    sa.Column('extension', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['module_key'], ['modules.module_key'], ),
    sa.ForeignKeyConstraint(['picklist_key'], ['picklists.picklist_key'], ),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('module_key', 'section_id', 'api_name', name='uq_field_metadata_qref')
    )
    op.create_index(op.f('ix_field_metadata_api_name'), 'field_metadata', ['api_name'], unique=False)
    op.create_index(op.f('ix_field_metadata_module_key'), 'field_metadata', ['module_key'], unique=False)
    op.create_index(op.f('ix_field_metadata_picklist_key'), 'field_metadata', ['picklist_key'], unique=False)
    op.create_index(op.f('ix_field_metadata_section_id'), 'field_metadata', ['section_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_field_metadata_section_id'), table_name='field_metadata')
    op.drop_index(op.f('ix_field_metadata_picklist_key'), table_name='field_metadata')
    op.drop_index(op.f('ix_field_metadata_module_key'), table_name='field_metadata')
    op.drop_index(op.f('ix_field_metadata_api_name'), table_name='field_metadata')
    op.drop_table('field_metadata')
    op.drop_table('stages')
    op.drop_index(op.f('ix_sections_module_key'), table_name='sections')
    op.drop_table('sections')
    op.drop_index(op.f('ix_picklist_values_picklist_key'), table_name='picklist_values')
    op.drop_table('picklist_values')
    op.drop_index(op.f('ix_metadata_versions_version_no'), table_name='metadata_versions')
    op.drop_table('metadata_versions')
    op.drop_table('picklists')
    op.drop_table('modules')


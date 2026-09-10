"""Baseline: the schema as Rounds 1-5 left it

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-09-03

The schema as it stood before Round 6, captured so that migration history has
a starting point.

Rounds 1 to 5 created their tables with Base.metadata.create_all() at app
startup, which is fine for standing a local database up and useless as a
record of how the schema got there. This revision is that record: it builds
every pre-Round-6 table exactly as the models declare them today.

ON AN EXISTING DATABASE, DO NOT RUN THIS — STAMP IT:

    alembic stamp 0001_baseline
    alembic upgrade head

The tables are already there; stamping tells Alembic so, and `upgrade head`
then applies only what came after. Running it against a populated database
would fail on the first CREATE TABLE, which is the safe way for it to fail.

On an empty database, `alembic upgrade head` runs this and everything after
it, and create_all() at startup then finds every table present and does
nothing.

Two tables that exist in some development databases are deliberately absent:
lead_secondary_suites and deal_expansion_suites, the junction tables behind
the two multiselects frozen to free text for Phase 1 (see models.Lead
.secondary_sap_suites). The models no longer declare them, so this baseline
does not create them and does not drop them either — an untouched leftover is
better than a migration that destroys data to tidy up.

There is no downgrade. The reverse of a baseline is an empty database.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001_baseline'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('id_sequences',
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('prefix', sa.String(length=10), nullable=False),
    sa.Column('pad', sa.Integer(), nullable=False),
    sa.Column('last_value', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.create_table('roles',
    sa.Column('role_id', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('role_id')
    )
    op.create_index(op.f('ix_roles_role_id'), 'roles', ['role_id'], unique=False)
    op.create_table('users',
    sa.Column('user_id', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_name'), 'users', ['name'], unique=False)
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=False)
    op.create_table('accounts',
    sa.Column('account_id', sa.String(length=20), nullable=False),
    sa.Column('account_name', sa.String(length=200), nullable=False),
    sa.Column('account_owner', sa.String(length=20), nullable=True),
    sa.Column('region', sa.String(length=40), nullable=True),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('segment', sa.String(length=40), nullable=True),
    sa.Column('customer_class', sa.String(length=60), nullable=True),
    sa.Column('account_target_phase', sa.String(length=40), nullable=True),
    sa.Column('partner_tier', sa.String(length=40), nullable=True),
    sa.Column('partner_type', sa.String(length=40), nullable=True),
    sa.Column('partner_satisfaction_score', sa.Numeric(precision=3, scale=1), nullable=True),
    sa.Column('engagement_cadence', sa.String(length=40), nullable=True),
    sa.Column('client_digital_strategy', sa.Text(), nullable=True),
    sa.Column('known_ot_it_stack', sa.Text(), nullable=True),
    sa.Column('active_tenders', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_owner'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('account_id')
    )
    op.create_index(op.f('ix_accounts_account_id'), 'accounts', ['account_id'], unique=False)
    op.create_index(op.f('ix_accounts_account_name'), 'accounts', ['account_name'], unique=False)
    op.create_index(op.f('ix_accounts_account_owner'), 'accounts', ['account_owner'], unique=False)
    op.create_table('user_roles',
    sa.Column('user_id', sa.String(length=20), nullable=False),
    sa.Column('role_id', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_table('account_types',
    sa.Column('account_id', sa.String(length=20), nullable=False),
    sa.Column('account_type', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.account_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', 'account_type')
    )
    op.create_table('contacts',
    sa.Column('contact_id', sa.String(length=20), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('job_title', sa.String(length=200), nullable=True),
    sa.Column('account', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('mobile', sa.String(length=50), nullable=True),
    sa.Column('linkedin', sa.String(length=300), nullable=True),
    sa.Column('contact_role', sa.String(length=40), nullable=True),
    sa.Column('engagement_owner', sa.String(length=20), nullable=True),
    sa.Column('relationship_score', sa.Numeric(precision=3, scale=1), nullable=True),
    sa.Column('friend_foe_assessment', sa.String(length=40), nullable=True),
    sa.Column('confidential', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_client_poc_evaluator', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['engagement_owner'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('contact_id')
    )
    op.create_index(op.f('ix_contacts_account'), 'contacts', ['account'], unique=False)
    op.create_index(op.f('ix_contacts_contact_id'), 'contacts', ['contact_id'], unique=False)
    op.create_index(op.f('ix_contacts_engagement_owner'), 'contacts', ['engagement_owner'], unique=False)
    op.create_index(op.f('ix_contacts_full_name'), 'contacts', ['full_name'], unique=False)
    op.create_table('leads',
    sa.Column('lead_id', sa.String(length=20), nullable=False),
    sa.Column('opportunity_name', sa.String(length=150), nullable=False),
    sa.Column('country', sa.String(length=120), nullable=True),
    sa.Column('city_state', sa.String(length=120), nullable=True),
    sa.Column('destination_region', sa.String(length=40), nullable=True),
    sa.Column('booking_region', sa.String(length=40), nullable=True),
    sa.Column('end_client', sa.String(length=20), nullable=True),
    sa.Column('customer_partner_si', sa.String(length=20), nullable=True),
    sa.Column('bd_owner', sa.String(length=20), nullable=True),
    sa.Column('primary_contact', sa.String(length=20), nullable=True),
    sa.Column('deal_source', sa.String(length=40), nullable=True),
    sa.Column('opportunity_type', sa.String(length=40), nullable=True),
    sa.Column('partner_deal_registration', sa.String(length=20), nullable=True),
    sa.Column('segment', sa.String(length=40), nullable=True),
    sa.Column('theme', sa.String(length=60), nullable=True),
    sa.Column('sap_solution_suite', sa.String(length=20), nullable=True),
    sa.Column('project_stage', sa.String(length=30), nullable=True),
    sa.Column('lead_status', sa.String(length=30), nullable=True),
    sa.Column('probability_pct', sa.Integer(), nullable=True),
    sa.Column('expected_close_month', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('fx_rate_at_entry', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('estimated_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('is_primary_pursuit', sa.Boolean(), nullable=False),
    sa.Column('parent_pursuit', sa.String(length=20), nullable=True),
    sa.Column('parent_deal', sa.String(length=20), nullable=True),
    sa.Column('incremental_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('remarks_notes', sa.Text(), nullable=True),
    sa.Column('lighthouse_project', sa.Boolean(), nullable=False),
    sa.Column('gorilla_flag', sa.Boolean(), nullable=False),
    sa.Column('demo_agreed', sa.Boolean(), nullable=False),
    sa.Column('demo_scheduled_date', sa.Date(), nullable=True),
    sa.Column('demo_completed', sa.Boolean(), nullable=False),
    sa.Column('demo_date', sa.Date(), nullable=True),
    sa.Column('suite_demonstrated', sa.String(length=20), nullable=True),
    sa.Column('interest_level', sa.String(length=20), nullable=True),
    sa.Column('data_site_access_confirmation_document', sa.String(length=255), nullable=True),
    sa.Column('pilot_commercial_model', sa.String(length=20), nullable=True),
    sa.Column('pilot_fee', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('client_feedback', sa.Text(), nullable=True),
    sa.Column('competitors_mentioned', sa.String(length=255), nullable=True),
    sa.Column('demo_debrief_notes', sa.Text(), nullable=True),
    sa.Column('poc_record', sa.String(length=20), nullable=True),
    sa.Column('poc_brief_gate', sa.String(length=20), nullable=True),
    sa.Column('secondary_sap_suites', sa.String(length=255), nullable=True),
    sa.Column('consultant_specifier', sa.String(length=20), nullable=True),
    sa.Column('sales_owner', sa.String(length=20), nullable=True),
    sa.Column('presales_owner', sa.String(length=20), nullable=True),
    sa.Column('client_phase', sa.String(length=30), nullable=True),
    sa.Column('project_team_access_confirmed', sa.Boolean(), nullable=False),
    sa.Column('budget_estimate', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('budget_confirmed', sa.Boolean(), nullable=False),
    sa.Column('probable_award_date', sa.Date(), nullable=True),
    sa.Column('pre_bid_alliance_partner', sa.String(length=20), nullable=True),
    sa.Column('alliance_structure', sa.String(length=40), nullable=True),
    sa.Column('pbaa_signed_date', sa.Date(), nullable=True),
    sa.Column('ctb_gate', sa.String(length=20), nullable=True),
    sa.Column('ctb_approval_status', sa.String(length=40), nullable=True),
    sa.Column('ctb_approval_date', sa.Date(), nullable=True),
    sa.Column('total_project_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('progression_pct', sa.Integer(), nullable=True),
    sa.Column('overall_rag', sa.String(length=10), nullable=True),
    sa.Column('next_milestone', sa.String(length=200), nullable=True),
    sa.Column('next_milestone_date', sa.Date(), nullable=True),
    sa.Column('stage_skip_reason', sa.String(length=500), nullable=True),
    sa.Column('stage_reversal_reason', sa.String(length=500), nullable=True),
    sa.Column('created_by', sa.String(length=20), nullable=True),
    sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('modified_by', sa.String(length=20), nullable=True),
    sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['bd_owner'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['consultant_specifier'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_partner_si'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['end_client'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['modified_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_pursuit'], ['leads.lead_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['pre_bid_alliance_partner'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['presales_owner'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['primary_contact'], ['contacts.contact_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sales_owner'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('lead_id')
    )
    op.create_index(op.f('ix_leads_bd_owner'), 'leads', ['bd_owner'], unique=False)
    op.create_index(op.f('ix_leads_consultant_specifier'), 'leads', ['consultant_specifier'], unique=False)
    op.create_index(op.f('ix_leads_created_by'), 'leads', ['created_by'], unique=False)
    op.create_index(op.f('ix_leads_customer_partner_si'), 'leads', ['customer_partner_si'], unique=False)
    op.create_index(op.f('ix_leads_end_client'), 'leads', ['end_client'], unique=False)
    op.create_index(op.f('ix_leads_modified_by'), 'leads', ['modified_by'], unique=False)
    op.create_index(op.f('ix_leads_parent_pursuit'), 'leads', ['parent_pursuit'], unique=False)
    op.create_index(op.f('ix_leads_pre_bid_alliance_partner'), 'leads', ['pre_bid_alliance_partner'], unique=False)
    op.create_index(op.f('ix_leads_presales_owner'), 'leads', ['presales_owner'], unique=False)
    op.create_index(op.f('ix_leads_primary_contact'), 'leads', ['primary_contact'], unique=False)
    op.create_index(op.f('ix_leads_sales_owner'), 'leads', ['sales_owner'], unique=False)
    op.create_table('lead_demo_attendees',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('lead_id', sa.String(length=20), nullable=False),
    sa.Column('row_order', sa.Integer(), nullable=False),
    sa.Column('attendee', sa.String(length=20), nullable=True),
    sa.Column('job_title', sa.String(length=100), nullable=True),
    sa.Column('organisation', sa.String(length=20), nullable=True),
    sa.Column('attendee_role', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['attendee'], ['contacts.contact_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.lead_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_demo_attendees_lead_id'), 'lead_demo_attendees', ['lead_id'], unique=False)
    op.create_table('lead_feature_gaps',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('lead_id', sa.String(length=20), nullable=False),
    sa.Column('row_order', sa.Integer(), nullable=False),
    sa.Column('gap_description', sa.Text(), nullable=True),
    sa.Column('suite_module', sa.String(length=20), nullable=True),
    sa.Column('impact', sa.String(length=40), nullable=True),
    sa.Column('raised_by', sa.String(length=20), nullable=True),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.lead_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['raised_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_feature_gaps_lead_id'), 'lead_feature_gaps', ['lead_id'], unique=False)
    op.create_table('opportunities',
    sa.Column('opportunity_id', sa.String(length=20), nullable=False),
    sa.Column('project_stage', sa.String(length=30), nullable=True),
    sa.Column('probability_pct', sa.Integer(), nullable=True),
    sa.Column('lead_status', sa.String(length=30), nullable=True),
    sa.Column('parent_lead', sa.String(length=20), nullable=True),
    sa.Column('fx_rate_at_entry', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('rfp_type', sa.String(length=40), nullable=True),
    sa.Column('rfp_received_date', sa.Date(), nullable=True),
    sa.Column('rfp_document', sa.String(length=255), nullable=True),
    sa.Column('submission_deadline', sa.DateTime(timezone=True), nullable=True),
    sa.Column('arr_annual_recurring', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('one_time_revenue', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('3rd_party_one_time', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('3rd_party_recurring_per_year', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contract_years', sa.Integer(), nullable=True),
    sa.Column('competitors_noticed', sa.String(length=255), nullable=True),
    sa.Column('bid_record', sa.String(length=20), nullable=True),
    sa.Column('bid_submission_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('debrief_requested_date', sa.Date(), nullable=True),
    sa.Column('platform_licence_list_price', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('services_and_implementation_cost', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('third_party_cost', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('cost_model_rcm_document', sa.String(length=255), nullable=True),
    sa.Column('licence_model', sa.String(length=40), nullable=True),
    sa.Column('perpetual_licence_fee', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('client_tender_reference', sa.String(length=60), nullable=True),
    sa.Column('primary_quote', sa.String(length=20), nullable=True),
    sa.Column('nomination_bid', sa.Boolean(), nullable=False),
    sa.Column('incumbent_only', sa.Boolean(), nullable=False),
    sa.Column('value_confidence', sa.String(length=40), nullable=True),
    sa.Column('bid_receipt_confirmed_date', sa.Date(), nullable=True),
    sa.Column('first_tbe_received_date', sa.Date(), nullable=True),
    sa.Column('technical_standing', sa.String(length=40), nullable=True),
    sa.Column('technical_approval_status', sa.String(length=40), nullable=True),
    sa.Column('technical_approval_date', sa.Date(), nullable=True),
    sa.Column('commercial_proposal_submitted_date', sa.Date(), nullable=True),
    sa.Column('final_negotiated_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contract_review_status', sa.String(length=40), nullable=True),
    sa.Column('contract_review_sign_off_date', sa.Date(), nullable=True),
    sa.Column('contract_review_sign_off_by', sa.String(length=20), nullable=True),
    sa.Column('commercial_gate', sa.String(length=20), nullable=True),
    sa.Column('award_type', sa.String(length=40), nullable=True),
    sa.Column('loi_received_date', sa.Date(), nullable=True),
    sa.Column('agreed_advance_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('agreed_credit_period_days', sa.Integer(), nullable=True),
    sa.Column('agreed_liability_cap_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('agreed_ld_cap_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('pay_when_paid', sa.Boolean(), nullable=False),
    sa.Column('sow_agreed_date', sa.Date(), nullable=True),
    sa.Column('bidder_declared_date', sa.Date(), nullable=True),
    sa.Column('progression_pct', sa.Integer(), nullable=True),
    sa.Column('overall_rag', sa.String(length=10), nullable=True),
    sa.Column('next_milestone', sa.String(length=200), nullable=True),
    sa.Column('next_milestone_date', sa.Date(), nullable=True),
    sa.Column('is_low_hanging', sa.Boolean(), nullable=False),
    sa.Column('low_hanging_rank', sa.Integer(), nullable=True),
    sa.Column('is_top_10', sa.Boolean(), nullable=False),
    sa.Column('top_10_rank', sa.Integer(), nullable=True),
    sa.Column('stage_skip_reason', sa.String(length=500), nullable=True),
    sa.Column('stage_reversal_reason', sa.String(length=500), nullable=True),
    sa.Column('created_by', sa.String(length=20), nullable=True),
    sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('modified_by', sa.String(length=20), nullable=True),
    sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['contract_review_sign_off_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['modified_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_lead'], ['leads.lead_id'], ),
    sa.PrimaryKeyConstraint('opportunity_id')
    )
    op.create_index(op.f('ix_opportunities_contract_review_sign_off_by'), 'opportunities', ['contract_review_sign_off_by'], unique=False)
    op.create_index(op.f('ix_opportunities_created_by'), 'opportunities', ['created_by'], unique=False)
    op.create_index(op.f('ix_opportunities_modified_by'), 'opportunities', ['modified_by'], unique=False)
    op.create_index(op.f('ix_opportunities_parent_lead'), 'opportunities', ['parent_lead'], unique=False)
    op.create_table('deals',
    sa.Column('deal_id', sa.String(length=20), nullable=False),
    sa.Column('deal_name', sa.String(length=200), nullable=False),
    sa.Column('parent_lead', sa.String(length=20), nullable=True),
    sa.Column('parent_opportunity', sa.String(length=20), nullable=True),
    sa.Column('end_client', sa.String(length=20), nullable=True),
    sa.Column('customer_partner_si', sa.String(length=20), nullable=True),
    sa.Column('deal_stage', sa.String(length=30), nullable=True),
    sa.Column('delivery_pm', sa.String(length=20), nullable=True),
    sa.Column('order_booked', sa.Boolean(), nullable=False),
    sa.Column('booking_date', sa.Date(), nullable=True),
    sa.Column('erp_reference', sa.String(length=100), nullable=True),
    sa.Column('po_loi_reference', sa.String(length=100), nullable=True),
    sa.Column('project_code', sa.String(length=60), nullable=True),
    sa.Column('contract_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('arr_annual_recurring', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('one_time_revenue', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('3rd_party_one_time', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('3rd_party_recurring_per_year', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contract_years', sa.Integer(), nullable=True),
    sa.Column('psp_completed_date', sa.Date(), nullable=True),
    sa.Column('handover_pack_delivered_date', sa.Date(), nullable=True),
    sa.Column('kickoff_meeting_date', sa.Date(), nullable=True),
    sa.Column('cash_flow_sign_off_date', sa.Date(), nullable=True),
    sa.Column('resource_plan_sign_off_date', sa.Date(), nullable=True),
    sa.Column('commissioning_date', sa.Date(), nullable=True),
    sa.Column('tandc_sign_off_date', sa.Date(), nullable=True),
    sa.Column('go_live_date', sa.Date(), nullable=True),
    sa.Column('warranty_start_date', sa.Date(), nullable=True),
    sa.Column('warranty_end_date', sa.Date(), nullable=True),
    sa.Column('contract_completion_date', sa.Date(), nullable=True),
    sa.Column('csat_score', sa.Numeric(precision=3, scale=1), nullable=True),
    sa.Column('csat_date', sa.Date(), nullable=True),
    sa.Column('reference_status', sa.String(length=40), nullable=True),
    sa.Column('reference_document', sa.String(length=255), nullable=True),
    sa.Column('re_engagement_30_day_date', sa.Date(), nullable=True),
    sa.Column('re_engagement_90_day_date', sa.Date(), nullable=True),
    sa.Column('expansion_suites', sa.String(length=255), nullable=True),
    sa.Column('incremental_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contract_expiry_date', sa.Date(), nullable=True),
    sa.Column('renewal_status', sa.String(length=40), nullable=True),
    sa.Column('renewal_signed_date', sa.Date(), nullable=True),
    sa.Column('created_by_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('modified_by_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['customer_partner_si'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['delivery_pm'], ['users.user_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['end_client'], ['accounts.account_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_lead'], ['leads.lead_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_opportunity'], ['opportunities.opportunity_id'], ),
    sa.PrimaryKeyConstraint('deal_id')
    )
    op.create_index(op.f('ix_deals_customer_partner_si'), 'deals', ['customer_partner_si'], unique=False)
    op.create_index(op.f('ix_deals_delivery_pm'), 'deals', ['delivery_pm'], unique=False)
    op.create_index(op.f('ix_deals_end_client'), 'deals', ['end_client'], unique=False)
    op.create_index(op.f('ix_deals_parent_lead'), 'deals', ['parent_lead'], unique=False)
    op.create_index(op.f('ix_deals_parent_opportunity'), 'deals', ['parent_opportunity'], unique=False)
    op.create_table('opportunity_payment_milestones',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('opportunity_id', sa.String(length=20), nullable=False),
    sa.Column('row_order', sa.Integer(), nullable=False),
    sa.Column('milestone', sa.String(length=60), nullable=True),
    sa.Column('pct_of_contract', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('trigger', sa.String(length=200), nullable=True),
    sa.Column('milestone_—_planned_date', sa.Date(), nullable=True),
    sa.Column('milestone_—_actual_date', sa.Date(), nullable=True),
    sa.Column('milestone_—_invoice_date', sa.Date(), nullable=True),
    sa.Column('milestone_—_payment_received_date', sa.Date(), nullable=True),
    sa.Column('milestone_status', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.opportunity_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_opportunity_payment_milestones_opportunity_id'), 'opportunity_payment_milestones', ['opportunity_id'], unique=False)
    op.create_table('deal_bid_commitments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('deal_id', sa.String(length=20), nullable=False),
    sa.Column('row_order', sa.Integer(), nullable=False),
    sa.Column('guarantee_—_type', sa.String(length=40), nullable=True),
    sa.Column('guarantee_—_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('guarantee_—_issue_date', sa.Date(), nullable=True),
    sa.Column('guarantee_—_expiry_date', sa.Date(), nullable=True),
    sa.Column('guarantee_—_issuing_bank', sa.String(length=200), nullable=True),
    sa.Column('guarantee_—_status', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.deal_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deal_bid_commitments_deal_id'), 'deal_bid_commitments', ['deal_id'], unique=False)
    op.create_table('deal_expansion_use_cases',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('deal_id', sa.String(length=20), nullable=False),
    sa.Column('row_order', sa.Integer(), nullable=False),
    sa.Column('use_case_no', sa.Integer(), nullable=True),
    sa.Column('use_case_description', sa.String(length=255), nullable=True),
    sa.Column('use_case_status', sa.String(length=40), nullable=True),
    sa.Column('estimated_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.deal_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deal_expansion_use_cases_deal_id'), 'deal_expansion_use_cases', ['deal_id'], unique=False)


def downgrade() -> None:
    raise NotImplementedError(
        "0001_baseline is the start of history. There is nothing below it to "
        "downgrade to — dropping every table is not a migration, it is a new "
        "database."
    )


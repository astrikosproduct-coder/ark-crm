from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: str
    name: str
    description: str | None = None
    sort_order: int
    active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    name: str
    email: EmailStr
    active: bool
    created_at: datetime
    updated_at: datetime
    roles: list[RoleOut] = []

    # Read from the directory on sign-in, so it is absent until that person has
    # signed in at least once — and stays absent if the tenant never sets it.
    employee_id: str | None = None
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    active: bool = True
    # Role ids assigned at creation. Empty is legal — a user with no role yet.
    role_ids: list[str] = []


class UserUpdate(BaseModel):
    """Every field optional — PATCH applies only what was sent."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    active: bool | None = None


class ActiveUpdate(BaseModel):
    active: bool


class RoleAssignment(BaseModel):
    """The full replacement set for PUT /users/{user_id}/roles."""

    role_ids: list[str]


class NextIdOut(BaseModel):
    user_id: str


class DirectoryUserOut(BaseModel):
    """
    A user as the rest of the prototype reads it, from GET /api/users.

    Shaped to match what spec/seed/users.json used to provide, so the 27
    user-lookup fields carry over unchanged. See routers/directory.py for why
    `id` is duplicated and why `roles` is flat. Email is a plain str here rather
    than EmailStr: this endpoint reports what is stored, and a directory read
    must not 500 because a legacy row holds an address that no longer validates.
    """

    id: str
    user_id: str
    name: str
    email: str
    active: bool
    roles: list[str]


# --------------------------------------------------------------- accounts

# The 17 register fields an account carries besides its id and the two
# multiselects. Listed once, so create/update/serialise cannot drift apart.
ACCOUNT_SCALARS = (
    "account_name",
    "account_owner",
    "region",
    "website",
    "phone",
    "address",
    "segment",
    "customer_class",
    "account_target_phase",
    "partner_tier",
    "partner_type",
    "partner_satisfaction_score",
    "engagement_cadence",
    "client_digital_strategy",
    "known_ot_it_stack",
    "active_tenders",
    "active",
)


class CustomFieldsMixin(BaseModel):
    """
    Carries the values of Administration-created fields into a write.

    Two doors, because there are two kinds of caller:

    `custom_fields`  an explicit object — {"rfp_document_file": "ABC.pdf"}.
        Every key must be an admin-created field on this module or the request
        is rejected. New code should use this.

    extra='allow'    the prototype's form engine sends ONE FLAT OBJECT
        (useRecordForm's toPayload), so an admin field arrives as a sibling of
        the register fields rather than nested. Allowing extras is what lets
        those through. It also lets `id`, `__labels` and computed values
        through, which is exactly why app/custom_fields.py takes only the keys
        field_metadata marks custom-stored and ignores the rest.

    Allowing extras changes nothing about the typed columns: every router
    writes those from its own *_SCALARS tuple, which no undeclared key can
    reach.
    """

    model_config = ConfigDict(extra="allow")

    custom_fields: dict[str, Any] | None = None


class AccountBase(CustomFieldsMixin):
    """
    Every field is optional except where the database itself insists.

    The register marks six of these Mandatory, but that is a stage-gating rule
    the form engine enforces — see the note on models.Account. Rejecting a
    half-filled account here would stop a reviewer saving the incomplete record
    that demonstrates the gap.
    """

    account_name: str | None = Field(default=None, max_length=200)
    account_owner: str | None = Field(default=None, max_length=20)
    region: str | None = None
    website: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    segment: str | None = None
    customer_class: str | None = None
    account_target_phase: str | None = None
    partner_tier: str | None = None
    partner_type: str | None = None
    partner_satisfaction_score: float | None = None
    engagement_cadence: str | None = None
    client_digital_strategy: str | None = None
    known_ot_it_stack: str | None = None
    active_tenders: str | None = None
    active: bool | None = None

    # The multiselect arrives as a list of picklist keys and is stored as
    # junction rows, never as a delimited string or JSONB.
    account_type: list[str] | None = None


class AccountCreate(AccountBase):
    account_name: str = Field(min_length=1, max_length=200)
    # Optional: the server allocates the next ACC-nnn when it is absent, which
    # is what the register's `autonumber` means. Supplied only by the migration.
    account_id: str | None = Field(default=None, max_length=20)


class AccountUpdate(AccountBase):
    """PATCH and PUT both use this; PATCH applies only what was sent."""


class AccountOut(BaseModel):
    """
    An account as the frontend reads it.

    `id` mirrors `account_id` for the same reason the user directory does it:
    src/lib/spec/index.ts idOf() reads `id`. `__labels` carries the resolved
    display name of each lookup, joined server-side so a page of 25 rows is one
    request rather than twenty-six — the contract src/mocks/query.ts defines.
    """

    # extra="allow" so a response can carry the values of
    # Administration-created fields. They are merged into the row flat, under
    # their api_name (see app/custom_fields.py::merge_into_row), and a
    # response_model drops every key it does not declare — which is exactly
    # what silently swallowed them before this was set. Declaring them is not
    # possible: which fields exist is decided at runtime, in the database.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    account_id: str
    account_name: str
    account_owner: str | None = None
    region: str | None = None
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    segment: str | None = None
    customer_class: str | None = None
    account_target_phase: str | None = None
    partner_tier: str | None = None
    partner_type: str | None = None
    partner_satisfaction_score: float | None = None
    engagement_cadence: str | None = None
    client_digital_strategy: str | None = None
    known_ot_it_stack: str | None = None
    active_tenders: str | None = None
    active: bool = True
    account_type: list[str] = []

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


# --------------------------------------------------------------- contacts

# The 14 register fields a contact carries besides its id.
CONTACT_SCALARS = (
    "full_name",
    "job_title",
    "account",
    "email",
    "phone",
    "mobile",
    "linkedin",
    "contact_role",
    "engagement_owner",
    "relationship_score",
    "friend_foe_assessment",
    "confidential",
    "is_client_poc_evaluator",
    "notes",
    "active",
)

# The lookups, and the collection each resolves against. Drives both the
# __labels join and the foreign-key check.
CONTACT_LOOKUPS = {"account": "accounts", "engagement_owner": "users"}


class ContactBase(CustomFieldsMixin):
    """
    Optional throughout, for the reason given on AccountBase: `Mandatory` in the
    register is a form-engine rule, not a storage constraint.

    email is a plain str rather than EmailStr — a contact record must be
    savable while a reviewer is still chasing the right address, and the form
    engine already flags the field's shape.
    """

    full_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    account: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    mobile: str | None = Field(default=None, max_length=50)
    linkedin: str | None = Field(default=None, max_length=300)
    contact_role: str | None = None
    engagement_owner: str | None = Field(default=None, max_length=20)
    relationship_score: float | None = None
    friend_foe_assessment: str | None = None
    confidential: bool | None = None
    is_client_poc_evaluator: bool | None = None
    notes: str | None = None
    active: bool | None = None


class ContactCreate(ContactBase):
    full_name: str = Field(min_length=1, max_length=200)
    # Absent means the server allocates the next CON-nnn, which is what the
    # register's `autonumber` means. Supplied only by the migration.
    contact_id: str | None = Field(default=None, max_length=20)


class ContactUpdate(ContactBase):
    """PATCH and PUT both use this; only the fields sent are applied."""


class ContactOut(BaseModel):
    """
    A contact as the frontend reads it. `id` mirrors `contact_id` for idOf(),
    and `__labels` carries the resolved Account name and Engagement Owner name
    so a page of rows is one request.
    """

    # extra="allow" so a response can carry the values of
    # Administration-created fields. They are merged into the row flat, under
    # their api_name (see app/custom_fields.py::merge_into_row), and a
    # response_model drops every key it does not declare — which is exactly
    # what silently swallowed them before this was set. Declaring them is not
    # possible: which fields exist is decided at runtime, in the database.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    contact_id: str
    full_name: str
    job_title: str | None = None
    account: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    linkedin: str | None = None
    contact_role: str | None = None
    engagement_owner: str | None = None
    relationship_score: float | None = None
    friend_foe_assessment: str | None = None
    confidential: bool = False
    is_client_poc_evaluator: bool = False
    notes: str | None = None
    active: bool = True

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


class ActiveFlag(BaseModel):
    """Body of PATCH /<collection>/{id}/active, mirroring the users endpoint."""

    active: bool


# --------------------------------------------------------------- leads

# Every real Lead column except lead_id and the secondary_sap_suites
# multiselect. Listed once so create/update/serialise cannot drift apart —
# same convention as ACCOUNT_SCALARS and CONTACT_SCALARS.
LEAD_SCALARS = (
    "opportunity_name",
    "country",
    "city_state",
    "destination_region",
    "booking_region",
    "end_client",
    "customer_partner_si",
    "bd_owner",
    "primary_contact",
    "deal_source",
    "opportunity_type",
    "partner_deal_registration",
    "segment",
    "theme",
    "sap_solution_suite",
    "project_stage",
    "lead_status",
    "probability_pct",
    "expected_close_month",
    "currency",
    "fx_rate_at_entry",
    "estimated_value",
    "is_primary_pursuit",
    "parent_pursuit",
    "parent_deal",
    "incremental_value",
    "remarks_notes",
    "lighthouse_project",
    "gorilla_flag",
    "demo_agreed",
    "demo_scheduled_date",
    "demo_completed",
    "demo_date",
    "suite_demonstrated",
    "secondary_sap_suites",
    "interest_level",
    "data_site_access_confirmation_document",
    "pilot_commercial_model",
    "pilot_fee",
    "client_feedback",
    "competitors_mentioned",
    "demo_debrief_notes",
    "poc_record",
    "poc_brief_gate",
    "consultant_specifier",
    "sales_owner",
    "presales_owner",
    "client_phase",
    "project_team_access_confirmed",
    "budget_estimate",
    "budget_confirmed",
    "probable_award_date",
    "pre_bid_alliance_partner",
    "alliance_structure",
    "pbaa_signed_date",
    "ctb_gate",
    "ctb_approval_status",
    "ctb_approval_date",
    "total_project_value",
    "progression_pct",
    "overall_rag",
    "next_milestone",
    "next_milestone_date",
    "stage_skip_reason",
    "stage_reversal_reason",
    "created_by",
    "modified_by",
    "active",
)

# The real foreign keys, and the collection each resolves against. Drives both
# the __labels join and the create/update existence check.
LEAD_LOOKUPS = {
    "end_client": "accounts",
    "customer_partner_si": "accounts",
    "consultant_specifier": "accounts",
    "pre_bid_alliance_partner": "accounts",
    "bd_owner": "users",
    "sales_owner": "users",
    "presales_owner": "users",
    "created_by": "users",
    "modified_by": "users",
    "primary_contact": "contacts",
    "parent_pursuit": "leads",
}

_MONEY_FIELDS = {
    "fx_rate_at_entry",
    "estimated_value",
    "incremental_value",
    "pilot_fee",
    "budget_estimate",
    "total_project_value",
}


class LeadDemoAttendeeIn(BaseModel):
    """One row of the demo_attendees childlist (spec/extensions.json
    leads.demo_attendees child_spec)."""

    model_config = ConfigDict(populate_by_name=True)

    attendee: str | None = Field(default=None, max_length=20)
    job_title: str | None = Field(default=None, max_length=100)
    organisation: str | None = Field(default=None, max_length=20)
    attendee_role: str | None = None


class LeadDemoAttendeeOut(LeadDemoAttendeeIn):
    pass


class LeadFeatureGapIn(BaseModel):
    """One row of the feature_gaps_logged childlist (spec/extensions.json
    leads.feature_gaps_logged child_spec)."""

    model_config = ConfigDict(populate_by_name=True)

    gap_description: str | None = None
    suite_module: str | None = Field(default=None, max_length=20)
    impact: str | None = None
    raised_by: str | None = Field(default=None, max_length=20)


class LeadFeatureGapOut(LeadFeatureGapIn):
    pass


class LeadBase(CustomFieldsMixin):
    """
    Optional throughout, for the reason AccountBase and ContactBase give:
    'Mandatory' in the register is a stage-gating rule the form engine enforces
    at transition time (see CLAUDE.md's four-layer check), not a storage
    constraint — a Stage-0 Lead missing its Stage-3 fields must still be
    savable.
    """

    opportunity_name: str | None = Field(default=None, max_length=150)
    country: str | None = Field(default=None, max_length=120)
    city_state: str | None = Field(default=None, max_length=120)
    destination_region: str | None = None
    booking_region: str | None = None
    end_client: str | None = Field(default=None, max_length=20)
    customer_partner_si: str | None = Field(default=None, max_length=20)
    bd_owner: str | None = Field(default=None, max_length=20)
    primary_contact: str | None = Field(default=None, max_length=20)
    deal_source: str | None = None
    opportunity_type: str | None = None
    partner_deal_registration: str | None = Field(default=None, max_length=20)
    segment: str | None = None
    theme: str | None = None
    sap_solution_suite: str | None = Field(default=None, max_length=20)
    project_stage: str | None = None
    lead_status: str | None = None
    probability_pct: int | None = None
    expected_close_month: date | None = None
    currency: str | None = Field(default=None, max_length=3)
    fx_rate_at_entry: float | None = None
    estimated_value: float | None = None
    is_primary_pursuit: bool | None = None
    parent_pursuit: str | None = Field(default=None, max_length=20)
    parent_deal: str | None = Field(default=None, max_length=20)
    incremental_value: float | None = None
    remarks_notes: str | None = None
    lighthouse_project: bool | None = None
    gorilla_flag: bool | None = None
    demo_agreed: bool | None = None
    demo_scheduled_date: date | None = None
    demo_completed: bool | None = None
    demo_date: date | None = None
    suite_demonstrated: str | None = Field(default=None, max_length=20)
    interest_level: str | None = None
    data_site_access_confirmation_document: str | None = Field(default=None, max_length=255)
    pilot_commercial_model: str | None = None
    pilot_fee: float | None = None
    client_feedback: str | None = None
    competitors_mentioned: str | None = Field(default=None, max_length=255)
    demo_debrief_notes: str | None = None
    poc_record: str | None = Field(default=None, max_length=20)
    poc_brief_gate: str | None = Field(default=None, max_length=20)
    # PHASE-1 FREEZE, 03 Sep 2026: was list[str] | None (a junction-table
    # multiselect of product ids) — see models.Lead.secondary_sap_suites.
    secondary_sap_suites: str | None = Field(default=None, max_length=255)
    consultant_specifier: str | None = Field(default=None, max_length=20)
    sales_owner: str | None = Field(default=None, max_length=20)
    presales_owner: str | None = Field(default=None, max_length=20)
    client_phase: str | None = None
    project_team_access_confirmed: bool | None = None
    budget_estimate: float | None = None
    budget_confirmed: bool | None = None
    probable_award_date: date | None = None
    pre_bid_alliance_partner: str | None = Field(default=None, max_length=20)
    alliance_structure: str | None = None
    pbaa_signed_date: date | None = None
    ctb_gate: str | None = Field(default=None, max_length=20)
    ctb_approval_status: str | None = None
    ctb_approval_date: date | None = None
    total_project_value: float | None = None
    progression_pct: int | None = None
    overall_rag: str | None = None
    next_milestone: str | None = Field(default=None, max_length=200)
    next_milestone_date: date | None = None
    stage_skip_reason: str | None = Field(default=None, max_length=500)
    stage_reversal_reason: str | None = Field(default=None, max_length=500)
    created_by: str | None = Field(default=None, max_length=20)
    modified_by: str | None = Field(default=None, max_length=20)
    active: bool | None = None

    # The two childlists — one row per attendee / gap, never a delimited
    # string, array column or JSONB, same rule secondary_sap_suites follows.
    demo_attendees: list[LeadDemoAttendeeIn] | None = None
    feature_gaps_logged: list[LeadFeatureGapIn] | None = None


class LeadCreate(LeadBase):
    opportunity_name: str = Field(min_length=1, max_length=150)
    # Optional: the server allocates the next LEAD-00nnn when it is absent,
    # which is what the register's `autonumber` means.
    lead_id: str | None = Field(default=None, max_length=20)


class LeadUpdate(LeadBase):
    """PATCH and PUT both use this; PATCH applies only what was sent."""


class LeadOut(BaseModel):
    """
    A Lead as the frontend reads it. `id` mirrors `lead_id` for idOf(), and
    `__labels` carries the resolved display name of every lookup so a page of
    rows is one request.

    contracting_party, days_in_current_stage and days_since_last_update are
    read-only, derived server-side from models.Lead's properties — they are
    never accepted on create/update.
    """

    # extra="allow" so a response can carry the values of
    # Administration-created fields. They are merged into the row flat, under
    # their api_name (see app/custom_fields.py::merge_into_row), and a
    # response_model drops every key it does not declare — which is exactly
    # what silently swallowed them before this was set. Declaring them is not
    # possible: which fields exist is decided at runtime, in the database.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    lead_id: str
    opportunity_name: str
    country: str | None = None
    city_state: str | None = None
    destination_region: str | None = None
    booking_region: str | None = None
    end_client: str | None = None
    customer_partner_si: str | None = None
    bd_owner: str | None = None
    primary_contact: str | None = None
    deal_source: str | None = None
    opportunity_type: str | None = None
    partner_deal_registration: str | None = None
    segment: str | None = None
    theme: str | None = None
    sap_solution_suite: str | None = None
    project_stage: str | None = None
    lead_status: str | None = None
    probability_pct: int | None = None
    expected_close_month: date | None = None
    currency: str | None = None
    fx_rate_at_entry: float | None = None
    estimated_value: float | None = None
    is_primary_pursuit: bool = True
    parent_pursuit: str | None = None
    parent_deal: str | None = None
    incremental_value: float | None = None
    remarks_notes: str | None = None
    lighthouse_project: bool = False
    gorilla_flag: bool = False
    demo_agreed: bool = False
    demo_scheduled_date: date | None = None
    demo_completed: bool = False
    demo_date: date | None = None
    suite_demonstrated: str | None = None
    interest_level: str | None = None
    data_site_access_confirmation_document: str | None = None
    pilot_commercial_model: str | None = None
    pilot_fee: float | None = None
    client_feedback: str | None = None
    competitors_mentioned: str | None = None
    demo_debrief_notes: str | None = None
    poc_record: str | None = None
    poc_brief_gate: str | None = None
    secondary_sap_suites: str | None = None
    consultant_specifier: str | None = None
    sales_owner: str | None = None
    presales_owner: str | None = None
    client_phase: str | None = None
    project_team_access_confirmed: bool = False
    budget_estimate: float | None = None
    budget_confirmed: bool = False
    probable_award_date: date | None = None
    pre_bid_alliance_partner: str | None = None
    alliance_structure: str | None = None
    pbaa_signed_date: date | None = None
    ctb_gate: str | None = None
    ctb_approval_status: str | None = None
    ctb_approval_date: date | None = None
    total_project_value: float | None = None
    progression_pct: int | None = None
    overall_rag: str | None = None
    next_milestone: str | None = None
    next_milestone_date: date | None = None
    stage_skip_reason: str | None = None
    stage_reversal_reason: str | None = None
    created_by: str | None = None
    created_date: datetime
    modified_by: str | None = None
    modified_date: datetime
    active: bool = True
    demo_attendees: list[LeadDemoAttendeeOut] = []
    feature_gaps_logged: list[LeadFeatureGapOut] = []

    # Derived, never stored.
    contracting_party: str | None = None
    days_in_current_stage: int = 0
    days_since_last_update: int = 0

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


# ------------------------------------------------------------ opportunities

# Every real Opportunity column except opportunity_id and the payment_
# milestones childlist. Python-friendly names throughout — third_party_one_
# time and third_party_recurring_per_year carry the register's real
# "3rd_party_*" name as their Pydantic `alias` below and their SQLAlchemy
# column name in models.py, since neither language accepts a leading digit.
OPPORTUNITY_SCALARS = (
    "project_stage",
    "probability_pct",
    "lead_status",
    "expected_close_month",
    "parent_lead",
    "fx_rate_at_entry",
    "rfp_type",
    "rfp_received_date",
    "rfp_document",
    "submission_deadline",
    "arr_annual_recurring",
    "one_time_revenue",
    "third_party_one_time",
    "third_party_recurring_per_year",
    "contract_years",
    "competitors_noticed",
    "bid_record",
    "bid_submission_date",
    "debrief_requested_date",
    "platform_licence_list_price",
    "services_and_implementation_cost",
    "third_party_cost",
    "cost_model_rcm_document",
    "licence_model",
    "perpetual_licence_fee",
    "client_tender_reference",
    "primary_quote",
    "nomination_bid",
    "incumbent_only",
    "value_confidence",
    "bid_receipt_confirmed_date",
    "first_tbe_received_date",
    "technical_standing",
    "technical_approval_status",
    "technical_approval_date",
    "commercial_proposal_submitted_date",
    "final_negotiated_value",
    "contract_review_status",
    "contract_review_sign_off_date",
    "contract_review_sign_off_by",
    "commercial_gate",
    "award_type",
    "loi_received_date",
    "agreed_advance_pct",
    "agreed_credit_period_days",
    "agreed_liability_cap_pct",
    "agreed_ld_cap_pct",
    "pay_when_paid",
    "sow_agreed_date",
    "bidder_declared_date",
    "progression_pct",
    "overall_rag",
    "next_milestone",
    "next_milestone_date",
    "is_low_hanging",
    "low_hanging_rank",
    "is_top_10",
    "top_10_rank",
    "stage_skip_reason",
    "stage_reversal_reason",
    "created_by",
    "modified_by",
    "active",
)

# The real foreign keys, and the collection each resolves against — bid_
# record, primary_quote and commercial_gate are NOT here, same reason Lead's
# poc_record/ctb_gate/parent_deal aren't in LEAD_LOOKUPS: those target tables
# (bids, quotes, gates) don't exist yet, so there is nothing to check or join.
OPPORTUNITY_LOOKUPS = {
    "parent_lead": "leads",
    "contract_review_sign_off_by": "users",
    "created_by": "users",
    "modified_by": "users",
}


class OpportunityPaymentMilestoneIn(BaseModel):
    """
    One row of the payment_milestones childlist. Four column names carry the
    register's own em dash and are therefore not valid Python identifiers —
    same accommodation as the model: plain-ASCII field name, register name as
    the Pydantic `alias`.
    """

    model_config = ConfigDict(populate_by_name=True)

    milestone: str | None = None
    pct_of_contract: float | None = None
    trigger: str | None = Field(default=None, max_length=200)
    milestone_planned_date: date | None = Field(default=None, alias="milestone_—_planned_date")
    milestone_actual_date: date | None = Field(default=None, alias="milestone_—_actual_date")
    milestone_invoice_date: date | None = Field(default=None, alias="milestone_—_invoice_date")
    milestone_payment_received_date: date | None = Field(
        default=None, alias="milestone_—_payment_received_date"
    )
    milestone_status: str | None = None


class OpportunityPaymentMilestoneOut(OpportunityPaymentMilestoneIn):
    pass


class OpportunityBase(CustomFieldsMixin):
    """
    Optional throughout, same reasoning LeadBase gives: 'Mandatory' in the
    register — payment_milestones included, despite being 'Mandatory' from
    Stage 6 — is a stage-gating rule the form engine enforces at transition
    time, not a storage constraint.
    """

    model_config = ConfigDict(populate_by_name=True)

    project_stage: str | None = None
    probability_pct: int | None = None
    lead_status: str | None = None
    expected_close_month: date | None = None
    parent_lead: str | None = Field(default=None, max_length=20)
    fx_rate_at_entry: float | None = None
    rfp_type: str | None = None
    rfp_received_date: date | None = None
    rfp_document: str | None = Field(default=None, max_length=255)
    submission_deadline: datetime | None = None
    arr_annual_recurring: float | None = None
    one_time_revenue: float | None = None
    third_party_one_time: float | None = Field(default=None, alias="3rd_party_one_time")
    third_party_recurring_per_year: float | None = Field(
        default=None, alias="3rd_party_recurring_per_year"
    )
    contract_years: int | None = None
    competitors_noticed: str | None = Field(default=None, max_length=255)
    bid_record: str | None = Field(default=None, max_length=20)
    bid_submission_date: datetime | None = None
    debrief_requested_date: date | None = None
    platform_licence_list_price: float | None = None
    services_and_implementation_cost: float | None = None
    third_party_cost: float | None = None
    cost_model_rcm_document: str | None = Field(default=None, max_length=255)
    licence_model: str | None = None
    perpetual_licence_fee: float | None = None
    client_tender_reference: str | None = Field(default=None, max_length=60)
    primary_quote: str | None = Field(default=None, max_length=20)
    nomination_bid: bool | None = None
    incumbent_only: bool | None = None
    value_confidence: str | None = None
    bid_receipt_confirmed_date: date | None = None
    first_tbe_received_date: date | None = None
    technical_standing: str | None = None
    technical_approval_status: str | None = None
    technical_approval_date: date | None = None
    commercial_proposal_submitted_date: date | None = None
    final_negotiated_value: float | None = None
    contract_review_status: str | None = None
    contract_review_sign_off_date: date | None = None
    contract_review_sign_off_by: str | None = Field(default=None, max_length=20)
    commercial_gate: str | None = Field(default=None, max_length=20)
    award_type: str | None = None
    loi_received_date: date | None = None
    agreed_advance_pct: float | None = None
    agreed_credit_period_days: int | None = None
    agreed_liability_cap_pct: float | None = None
    agreed_ld_cap_pct: float | None = None
    pay_when_paid: bool | None = None
    sow_agreed_date: date | None = None
    bidder_declared_date: date | None = None
    progression_pct: int | None = None
    overall_rag: str | None = None
    next_milestone: str | None = Field(default=None, max_length=200)
    next_milestone_date: date | None = None
    # is_low_hanging/is_top_10/their ranks are accepted here for symmetry with
    # every other field, but the router validates them through
    # app.priority_flags rather than writing them straight through — see
    # routers/opportunities.py.
    is_low_hanging: bool | None = None
    low_hanging_rank: int | None = None
    is_top_10: bool | None = None
    top_10_rank: int | None = None
    stage_skip_reason: str | None = Field(default=None, max_length=500)
    stage_reversal_reason: str | None = Field(default=None, max_length=500)
    created_by: str | None = Field(default=None, max_length=20)
    modified_by: str | None = Field(default=None, max_length=20)
    active: bool | None = None

    # The childlist — one row per payment milestone, never a delimited
    # string, array column or JSONB, same rule secondary_sap_suites follows.
    payment_milestones: list[OpportunityPaymentMilestoneIn] | None = None


class OpportunityCreate(OpportunityBase):
    # Optional: the server allocates the next OPP-00nnn when it is absent.
    opportunity_id: str | None = Field(default=None, max_length=20)


class OpportunityUpdate(OpportunityBase):
    """PATCH and PUT both use this; PATCH applies only what was sent."""


class OpportunityOut(BaseModel):
    """An Opportunity as the frontend reads it. `id` mirrors `opportunity_id`
    for idOf(), and `__labels` carries the resolved display name of every
    lookup so a page of rows is one request."""

    # extra="allow" so a response can carry the values of
    # Administration-created fields. They are merged into the row flat, under
    # their api_name (see app/custom_fields.py::merge_into_row), and a
    # response_model drops every key it does not declare — which is exactly
    # what silently swallowed them before this was set. Declaring them is not
    # possible: which fields exist is decided at runtime, in the database.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    opportunity_id: str
    project_stage: str | None = None
    probability_pct: int | None = None
    lead_status: str | None = None
    expected_close_month: date | None = None
    parent_lead: str | None = None
    fx_rate_at_entry: float | None = None
    rfp_type: str | None = None
    rfp_received_date: date | None = None
    rfp_document: str | None = None
    submission_deadline: datetime | None = None
    arr_annual_recurring: float | None = None
    one_time_revenue: float | None = None
    third_party_one_time: float | None = Field(default=None, alias="3rd_party_one_time")
    third_party_recurring_per_year: float | None = Field(
        default=None, alias="3rd_party_recurring_per_year"
    )
    contract_years: int | None = None
    competitors_noticed: str | None = None
    bid_record: str | None = None
    bid_submission_date: datetime | None = None
    debrief_requested_date: date | None = None
    platform_licence_list_price: float | None = None
    services_and_implementation_cost: float | None = None
    third_party_cost: float | None = None
    cost_model_rcm_document: str | None = None
    licence_model: str | None = None
    perpetual_licence_fee: float | None = None
    client_tender_reference: str | None = None
    primary_quote: str | None = None
    nomination_bid: bool = False
    incumbent_only: bool = False
    value_confidence: str | None = None
    bid_receipt_confirmed_date: date | None = None
    first_tbe_received_date: date | None = None
    technical_standing: str | None = None
    technical_approval_status: str | None = None
    technical_approval_date: date | None = None
    commercial_proposal_submitted_date: date | None = None
    final_negotiated_value: float | None = None
    contract_review_status: str | None = None
    contract_review_sign_off_date: date | None = None
    contract_review_sign_off_by: str | None = None
    commercial_gate: str | None = None
    award_type: str | None = None
    loi_received_date: date | None = None
    agreed_advance_pct: float | None = None
    agreed_credit_period_days: int | None = None
    agreed_liability_cap_pct: float | None = None
    agreed_ld_cap_pct: float | None = None
    pay_when_paid: bool = False
    sow_agreed_date: date | None = None
    bidder_declared_date: date | None = None
    progression_pct: int | None = None
    overall_rag: str | None = None
    next_milestone: str | None = None
    next_milestone_date: date | None = None
    is_low_hanging: bool = False
    low_hanging_rank: int | None = None
    is_top_10: bool = False
    top_10_rank: int | None = None
    stage_skip_reason: str | None = None
    stage_reversal_reason: str | None = None
    created_by: str | None = None
    created_date: datetime
    modified_by: str | None = None
    modified_date: datetime
    active: bool = True
    payment_milestones: list[OpportunityPaymentMilestoneOut] = []

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


# --------------------------------------------------------------- deals

# Every real Deal column except deal_id and the two childlists. guarantee_—_*
# are NOT here — see models.Deal's docstring: they are columns of
# bid_commitments_register, not scalars. expansion_suites IS here, PHASE-1
# FREEZE (03 Sep 2026) — see models.Deal.expansion_suites.
DEAL_SCALARS = (
    "deal_name",
    "parent_lead",
    "parent_opportunity",
    "end_client",
    "customer_partner_si",
    "deal_stage",
    "expected_close_month",
    "delivery_pm",
    "order_booked",
    "booking_date",
    "erp_reference",
    "po_loi_reference",
    "project_code",
    "contract_value",
    "arr_annual_recurring",
    "one_time_revenue",
    "third_party_one_time",
    "third_party_recurring_per_year",
    "contract_years",
    "psp_completed_date",
    "handover_pack_delivered_date",
    "kickoff_meeting_date",
    "cash_flow_sign_off_date",
    "resource_plan_sign_off_date",
    "commissioning_date",
    "tandc_sign_off_date",
    "go_live_date",
    "warranty_start_date",
    "warranty_end_date",
    "contract_completion_date",
    "csat_score",
    "csat_date",
    "reference_status",
    "reference_document",
    "re_engagement_30_day_date",
    "re_engagement_90_day_date",
    "expansion_suites",
    "incremental_value",
    "contract_expiry_date",
    "renewal_status",
    "renewal_signed_date",
    "active",
)

# The real foreign keys, and the collection each resolves against.
# Neither parent_lead nor parent_opportunity is a spec/fields.json row for
# module=deals/opportunities respectively — both are synthetic identity links
# moduleSplit.ts injects — but Opportunity.parent_lead is still a normal
# PATCH-able scalar (see OPPORTUNITY_SCALARS), so parent_opportunity follows
# the same precedent here rather than being special-cased.
DEAL_LOOKUPS = {
    "parent_lead": "leads",
    "parent_opportunity": "opportunities",
    "end_client": "accounts",
    "customer_partner_si": "accounts",
    "delivery_pm": "users",
}


class DealBidCommitmentIn(BaseModel):
    """
    One row of bid_commitments_register. Seven register column names carry
    the em dash and are therefore not valid Python identifiers — same
    accommodation as OpportunityPaymentMilestoneIn: plain-ASCII field name,
    register name as the Pydantic `alias`.

    guarantee_—_pct_of_contract_value is not a field here — it is computed,
    never stored, same rule the model follows.
    """

    model_config = ConfigDict(populate_by_name=True)

    guarantee_type: str | None = Field(default=None, alias="guarantee_—_type")
    guarantee_value: float | None = Field(default=None, alias="guarantee_—_value")
    guarantee_issue_date: date | None = Field(default=None, alias="guarantee_—_issue_date")
    guarantee_expiry_date: date | None = Field(default=None, alias="guarantee_—_expiry_date")
    guarantee_issuing_bank: str | None = Field(default=None, alias="guarantee_—_issuing_bank")
    guarantee_status: str | None = Field(default=None, alias="guarantee_—_status")


class DealBidCommitmentOut(DealBidCommitmentIn):
    pass


class DealExpansionUseCaseIn(BaseModel):
    use_case_no: int | None = None
    use_case_description: str | None = Field(default=None, max_length=255)
    use_case_status: str | None = None
    estimated_value: float | None = None


class DealExpansionUseCaseOut(DealExpansionUseCaseIn):
    pass


class DealBase(CustomFieldsMixin):
    """
    Optional throughout, same reasoning LeadBase and OpportunityBase give:
    'Mandatory' in the register is a stage-gating rule the form engine
    enforces at transition time, not a storage constraint.
    """

    model_config = ConfigDict(populate_by_name=True)

    deal_name: str | None = Field(default=None, max_length=200)
    parent_lead: str | None = Field(default=None, max_length=20)
    parent_opportunity: str | None = Field(default=None, max_length=20)
    end_client: str | None = Field(default=None, max_length=20)
    customer_partner_si: str | None = Field(default=None, max_length=20)
    deal_stage: str | None = None
    expected_close_month: date | None = None
    delivery_pm: str | None = Field(default=None, max_length=20)
    order_booked: bool | None = None
    booking_date: date | None = None
    erp_reference: str | None = Field(default=None, max_length=100)
    po_loi_reference: str | None = Field(default=None, max_length=100)
    project_code: str | None = Field(default=None, max_length=60)
    contract_value: float | None = None
    arr_annual_recurring: float | None = None
    one_time_revenue: float | None = None
    third_party_one_time: float | None = Field(default=None, alias="3rd_party_one_time")
    third_party_recurring_per_year: float | None = Field(
        default=None, alias="3rd_party_recurring_per_year"
    )
    contract_years: int | None = None
    psp_completed_date: date | None = None
    handover_pack_delivered_date: date | None = None
    kickoff_meeting_date: date | None = None
    cash_flow_sign_off_date: date | None = None
    resource_plan_sign_off_date: date | None = None
    commissioning_date: date | None = None
    tandc_sign_off_date: date | None = None
    go_live_date: date | None = None
    warranty_start_date: date | None = None
    warranty_end_date: date | None = None
    contract_completion_date: date | None = None
    csat_score: float | None = None
    csat_date: date | None = None
    reference_status: str | None = None
    reference_document: str | None = Field(default=None, max_length=255)
    re_engagement_30_day_date: date | None = None
    re_engagement_90_day_date: date | None = None
    # PHASE-1 FREEZE, 03 Sep 2026: was list[str] | None (a junction-table
    # multiselect of free strings) — see models.Deal.expansion_suites.
    expansion_suites: str | None = Field(default=None, max_length=255)
    incremental_value: float | None = None
    contract_expiry_date: date | None = None
    renewal_status: str | None = None
    renewal_signed_date: date | None = None
    active: bool | None = None

    # The two childlists — one row per commitment/use case, never a delimited
    # string, array column or JSONB, same rule payment_milestones follows.
    bid_commitments_register: list[DealBidCommitmentIn] | None = None
    expansion_use_cases: list[DealExpansionUseCaseIn] | None = None


class DealCreate(DealBase):
    # Optional: the server allocates the next DEAL-00nnn when it is absent.
    deal_id: str | None = Field(default=None, max_length=20)


class DealUpdate(DealBase):
    """PATCH and PUT both use this; PATCH applies only what was sent."""


class DealOut(BaseModel):
    """A Deal as the frontend reads it. `id` mirrors `deal_id` for idOf(), and
    `__labels` carries the resolved display name of every lookup so a page of
    rows is one request."""

    # extra="allow" so a response can carry the values of
    # Administration-created fields. They are merged into the row flat, under
    # their api_name (see app/custom_fields.py::merge_into_row), and a
    # response_model drops every key it does not declare — which is exactly
    # what silently swallowed them before this was set. Declaring them is not
    # possible: which fields exist is decided at runtime, in the database.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    deal_id: str
    deal_name: str
    parent_lead: str | None = None
    parent_opportunity: str | None = None
    end_client: str | None = None
    customer_partner_si: str | None = None
    deal_stage: str | None = None
    expected_close_month: date | None = None
    delivery_pm: str | None = None
    order_booked: bool = False
    booking_date: date | None = None
    erp_reference: str | None = None
    po_loi_reference: str | None = None
    project_code: str | None = None
    contract_value: float | None = None
    arr_annual_recurring: float | None = None
    one_time_revenue: float | None = None
    third_party_one_time: float | None = Field(default=None, alias="3rd_party_one_time")
    third_party_recurring_per_year: float | None = Field(
        default=None, alias="3rd_party_recurring_per_year"
    )
    contract_years: int | None = None
    psp_completed_date: date | None = None
    handover_pack_delivered_date: date | None = None
    kickoff_meeting_date: date | None = None
    cash_flow_sign_off_date: date | None = None
    resource_plan_sign_off_date: date | None = None
    commissioning_date: date | None = None
    tandc_sign_off_date: date | None = None
    go_live_date: date | None = None
    warranty_start_date: date | None = None
    warranty_end_date: date | None = None
    contract_completion_date: date | None = None
    csat_score: float | None = None
    csat_date: date | None = None
    reference_status: str | None = None
    reference_document: str | None = None
    re_engagement_30_day_date: date | None = None
    re_engagement_90_day_date: date | None = None
    expansion_suites: str | None = None
    incremental_value: float | None = None
    contract_expiry_date: date | None = None
    renewal_status: str | None = None
    renewal_signed_date: date | None = None
    created_by_date: datetime
    modified_by_date: datetime
    active: bool = True
    bid_commitments_register: list[DealBidCommitmentOut] = []
    expansion_use_cases: list[DealExpansionUseCaseOut] = []

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


# --------------------------------------------------------------- stage transitions

class TransitionCreate(BaseModel):
    """POST /api/transitions body — mirrors lib/pipeline.ts's Transition interface."""

    model_config = ConfigDict(populate_by_name=True)

    module: str
    record_id: str
    from_stage: int = Field(alias="from")
    to_stage: int = Field(alias="to")
    reason: str | None = None
    is_skip: bool = False
    is_reversal: bool = False
    actor: str | None = None
    timestamp: datetime


class TransitionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    module: str
    record_id: str
    from_stage: int = Field(alias="from")
    to_stage: int = Field(alias="to")
    reason: str | None
    is_skip: bool
    is_reversal: bool
    actor: str | None
    timestamp: datetime


# --------------------------------------------------------------- conversions

class ConversionCreate(BaseModel):
    """POST /api/conversions body, as posted by LeadAdvanceDialog.tsx and
    opportunities/ConvertToDealDialog.tsx today."""

    source_module: str
    source_id: str
    target_module: str
    target_id: str
    actor: str | None = None
    timestamp: datetime
    copied_fields: list[str] = []
    note: str | None = None


class ConversionOut(BaseModel):
    id: str
    source_module: str
    source_id: str
    target_module: str
    target_id: str
    actor: str | None
    timestamp: datetime
    copied_fields: list[str]
    note: str | None


# --------------------------------------------------------------- audit log

class AuditLogOut(BaseModel):
    """
    No AuditLogCreate: rows are written from inside the leads/opportunities/
    deals/accounts/contacts routers' own handlers (app/audit.py), never from a
    public POST — a client cannot write its own audit trail.
    """

    id: str
    record_module: str
    record_id: str
    action: str
    actor: str | None
    changed_fields: list[str] | None
    timestamp: datetime


# --------------------------------------------------------------- deal registrations

# The 14 register fields a registration carries besides its id. Described by
# the register under module `partners`, section DEAL REGISTRATION — see
# models.DealRegistration.
REGISTRATION_SCALARS = (
    "partner",
    "end_client",
    "project_name",
    "estimated_value",
    "expected_timeline",
    "partner_role",
    "submitted_date",
    "acknowledged_date",
    "acknowledgement_sla_met",
    "exclusivity_start_date",
    "exclusivity_expiry_date",
    "registration_status",
    "extension_reason",
    "linked_lead",
)

REGISTRATION_LOOKUPS = {"partner": "accounts", "end_client": "accounts", "linked_lead": "leads"}


class DealRegistrationBase(CustomFieldsMixin):
    """Optional throughout — `Mandatory` in the register is a form-engine rule,
    not a storage constraint; see AccountBase for the same reasoning."""

    partner: str | None = Field(default=None, max_length=20)
    end_client: str | None = Field(default=None, max_length=20)
    project_name: str | None = Field(default=None, max_length=150)
    estimated_value: float | None = None
    expected_timeline: str | None = Field(default=None, max_length=100)
    partner_role: str | None = Field(default=None, max_length=40)
    submitted_date: date | None = None
    acknowledged_date: date | None = None
    acknowledgement_sla_met: bool | None = None
    exclusivity_start_date: date | None = None
    exclusivity_expiry_date: date | None = None
    registration_status: str | None = Field(default=None, max_length=40)
    extension_reason: str | None = Field(default=None, max_length=500)
    linked_lead: str | None = Field(default=None, max_length=20)


class DealRegistrationCreate(DealRegistrationBase):
    # Absent means the server allocates the next REG-nnnnn.
    registration_id: str | None = Field(default=None, max_length=20)


class DealRegistrationUpdate(DealRegistrationBase):
    """PATCH and PUT both use this; only the fields sent are applied."""


class DealRegistrationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    registration_id: str
    partner: str | None = None
    end_client: str | None = None
    project_name: str | None = None
    estimated_value: float | None = None
    expected_timeline: str | None = None
    partner_role: str | None = None
    submitted_date: date | None = None
    acknowledged_date: date | None = None
    acknowledgement_sla_met: bool | None = None
    exclusivity_start_date: date | None = None
    exclusivity_expiry_date: date | None = None
    registration_status: str | None = None
    extension_reason: str | None = None
    linked_lead: str | None = None

    labels: dict[str, str] | None = Field(default=None, alias="__labels")


# --------------------------------------------------------------- registration conflicts

# Described by the register under module `partners`, section CONFLICT
# ADJUDICATION — see models.RegistrationConflict.
CONFLICT_SCALARS = (
    "registration_a",
    "registration_b",
    "who_registered_first",
    "stronger_client_relationship",
    "better_delivery_capability",
    "decision",
    "decision_date",
    "decided_by",
    "both_partners_notified",
)

CONFLICT_LOOKUPS = {
    "registration_a": "registrations",
    "registration_b": "registrations",
    "decided_by": "users",
}


class RegistrationConflictBase(CustomFieldsMixin):
    registration_a: str | None = Field(default=None, max_length=20)
    registration_b: str | None = Field(default=None, max_length=20)
    who_registered_first: str | None = Field(default=None, max_length=300)
    stronger_client_relationship: str | None = Field(default=None, max_length=300)
    better_delivery_capability: str | None = Field(default=None, max_length=300)
    decision: str | None = Field(default=None, max_length=40)
    decision_date: date | None = None
    decided_by: str | None = Field(default=None, max_length=20)
    both_partners_notified: bool | None = None


class RegistrationConflictCreate(RegistrationConflictBase):
    # Absent means the server allocates the next CONF-nnnn.
    conflict_id: str | None = Field(default=None, max_length=20)


class RegistrationConflictUpdate(RegistrationConflictBase):
    """PATCH and PUT both use this; only the fields sent are applied."""


class RegistrationConflictOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    conflict_id: str
    registration_a: str | None = None
    registration_b: str | None = None
    who_registered_first: str | None = None
    stronger_client_relationship: str | None = None
    better_delivery_capability: str | None = None
    decision: str | None = None
    decision_date: date | None = None
    decided_by: str | None = None
    both_partners_notified: bool = False

    labels: dict[str, str] | None = Field(default=None, alias="__labels")

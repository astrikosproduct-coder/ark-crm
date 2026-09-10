from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================================
# TWO WAYS A FIELD'S VALUE IS STORED
# =========================================================================
#
# Register fields — the 566 rows the workbook defines — are TYPED COLUMNS.
# leads.opportunity_name is a VARCHAR(150), leads.end_client is a real foreign
# key into accounts. They are known at migration time, so they get the type
# checking, the constraints and the cheap indexing that a column gives.
#
# Fields created through the Administration Module are NOT known at migration
# time. Giving each one a column would mean ALTER TABLE from an admin screen,
# which is the mirror image of the DROP COLUMN that Round 6 refuses to do. So
# their values live in `custom_fields`, a JSONB column on each business table,
# keyed by the field's api_name:
#
#     custom_fields = {"rfp_document_file": "ABC.pdf", "customer_priority": "High"}
#
# Which of the two a field uses is NOT inferred from whether a key looks
# familiar. field_metadata.storage records it explicitly — see that column.
#
# The trade is deliberate and it runs both ways. JSONB gives up type checking,
# foreign keys and cheap indexing; that is the right price for a field nobody
# could have declared in advance, and the wrong price for `end_client`, which
# already has working referential integrity worth keeping. Neither storage mode
# is being migrated into the other.
#
# NOT TO BE CONFUSED WITH THE ROUND-6 METADATA JSONB, which answers a different
# question entirely:
#
#   business_table.custom_fields   what did THIS record answer for admin fields?
#   metadata_versions.snapshot     what did the CONFIGURATION look like on 3 Sep?
#   field_metadata.extension       does this field DEFINITION have a sidecar entry?
#
# Only the first holds data a CRM user typed.


def _custom_fields_column() -> Mapped[dict]:
    """
    The dynamic-value store, identical on every business table.

    NOT NULL with a '{}' default rather than nullable: every read path can then
    treat it as a dict without a None check, and a record that has never been
    given an admin-created value is `{}` rather than an absence that each caller
    has to interpret for itself.
    """
    return mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class User(Base):
    """
    A CRM user.

    user_id is the natural primary key and carries the workbook's USR-001
    reference style directly, so user_roles rows stay readable in psql. The
    Administration screen suggests the next USR-00N but the admin may overwrite
    it, which is why this is a VARCHAR the caller supplies rather than a
    sequence.
    """

    __tablename__ = "users"

    user_id = Column(String(20), primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True, server_default="true")

    # The Microsoft directory identity, once this row has been linked by a
    # successful sign-in. Holds the `oid` claim — the object id of the user in
    # the TENANT — never `sub`, which is issued per app registration and would
    # stop matching the moment the registration changes. See migration
    # 0011_entra_sso for why that distinction is load-bearing here.
    entra_object_id = Column(String(64), unique=True, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # HR's identifier for this person, read from Microsoft Graph on sign-in.
    # An attribute for display and reconciliation only — never an identifier:
    # it is nullable by nature (many tenants never populate it) and editable by
    # HR, which is exactly what an identity key must not be. See migration
    # 0012_employee_id.
    employee_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    roles = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        order_by="Role.sort_order",
        lazy="selectin",
    )


class Role(Base):
    """
    A system-defined role.

    role_id holds the picklist key from spec/picklists.json
    (administration__roles) — BD_OWNER, APPROVER and so on — so the database and
    the field register agree on one vocabulary. Roles are seeded, never created
    through the API.
    """

    __tablename__ = "roles"

    role_id = Column(String(30), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    users = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base):
    """
    The Roles multiselect, as a junction table rather than an array or JSONB
    column — one row per assignment, composite primary key.
    """

    __tablename__ = "user_roles"

    user_id = Column(
        String(20),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id = Column(
        String(30),
        ForeignKey("roles.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Account(Base):
    """
    An organisation. End Clients and Partners are BOTH accounts — there is no
    second organisation table, and Partners is a view over this one filtered by
    account_type (see extensions.json list_views.partners).

    The 18 Phase-1 register fields map to real columns here, except the
    account_type multiselect, which gets a junction table below. Nothing is
    stored in JSONB.

    (Platform Depth was a nineteenth field. It named no picklist, so it could
    never hold a value, and it was deleted from the register on request — see
    extensions.json open_questions, accounts.platform_depth.)

    Picklist columns hold the KEY from spec/picklists.json — 'INFRASTRUCTURE',
    not 'Infrastructure'. The frontend renders labels from that file, which
    stays the single vocabulary; the database does not duplicate it.

    Note on nullability: the register marks account_name, account_owner,
    region, segment, customer_class and account_target_phase Mandatory, but
    only account_name is NOT NULL here. 'Mandatory' in the register is a
    stage-gating rule enforced by the form engine and validateForTransition,
    not a storage constraint — a half-filled account must be savable, or the
    prototype cannot show the very gap it exists to find.
    """

    __tablename__ = "accounts"

    account_id = Column(String(20), primary_key=True, index=True)
    account_name = Column(String(200), nullable=False, index=True)

    # The one real relationship: an owner is a row in the users table.
    account_owner = Column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # CORE
    region = Column(String(40), nullable=True)
    website = Column(String(300), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)

    # CLASSIFICATION
    segment = Column(String(40), nullable=True)
    customer_class = Column(String(60), nullable=True)
    account_target_phase = Column(String(40), nullable=True)

    # PARTNER ATTRIBUTES
    partner_tier = Column(String(40), nullable=True)
    partner_type = Column(String(40), nullable=True)
    partner_satisfaction_score = Column(Numeric(3, 1), nullable=True)
    engagement_cadence = Column(String(40), nullable=True)

    # RESEARCH
    client_digital_strategy = Column(Text, nullable=True)
    known_ot_it_stack = Column(Text, nullable=True)
    active_tenders = Column(Text, nullable=True)

    # NOT A REGISTER FIELD. The workbook gives an account no active flag; this
    # was added on request so an account that other records depend on can be
    # retired without being destroyed. Recorded as a register correction in
    # extensions.json open_questions, ref accounts.active.
    active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # Values for fields created through the Administration Module, keyed by
    # api_name. See the TWO WAYS A FIELD'S VALUE IS STORED note at the top.
    custom_fields: Mapped[dict] = _custom_fields_column()

    owner = relationship("User", lazy="joined")
    types = relationship(
        "AccountType",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="account",
    )


class AccountType(Base):
    """
    accounts.account_type — a multiselect, so one row per selected value rather
    than a delimited string, an array column or JSONB. Same rule the Roles
    multiselect follows in user_roles.

    account_type holds a key from the accounts__account_type picklist:
    END_CLIENT, PARTNER_SI, CONSULTANT_SPECIFIER, OEM_TECHNOLOGY_PARTNER,
    SECTOR_SPECIALIST. This is what makes an account a Partner.
    """

    __tablename__ = "account_types"

    account_id = Column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        primary_key=True,
    )
    account_type = Column(String(40), primary_key=True)

    account = relationship("Account", back_populates="types")


class Contact(Base):
    """
    An external person at an Account.

    Users are internal ARK employees and live in `users`; contacts are the
    client-side people and live here. The two are never mixed — a contact has
    no login and holds no role, and an engagement_owner is a USER, not another
    contact.

    Fifteen register fields, all scalar: Contacts carries no multiselect, so
    unlike accounts it needs no junction table. Nothing is stored in JSONB.

    Two real foreign keys:
      * account          -> accounts.account_id
      * engagement_owner -> users.user_id

    Both are ON DELETE SET NULL rather than CASCADE. Deleting an organisation
    or an employee must not silently delete the people recorded against them —
    the contact survives with the link cleared, which is visible on the screen
    and recoverable, where a vanished row is neither.

    The column is `account`, not `account_id`: every column here is named after
    its register api_name, the same rule accounts.account_owner follows. The
    relationship is identical either way, and matching the api_name means the
    API needs no translation layer between the database and the form engine.
    """

    __tablename__ = "contacts"

    contact_id = Column(String(20), primary_key=True, index=True)

    # CORE
    full_name = Column(String(200), nullable=False, index=True)
    job_title = Column(String(200), nullable=True)
    account = Column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    mobile = Column(String(50), nullable=True)
    linkedin = Column(String(300), nullable=True)

    # ROLE & RELATIONSHIP
    contact_role = Column(String(40), nullable=True)
    engagement_owner = Column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    relationship_score = Column(Numeric(3, 1), nullable=True)
    friend_foe_assessment = Column(String(40), nullable=True)
    confidential = Column(Boolean, nullable=False, default=False, server_default="false")
    is_client_poc_evaluator = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notes = Column(Text, nullable=True)

    # NOT A REGISTER FIELD - same story as accounts.active, same correction row.
    active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    # Values for fields created through the Administration Module, keyed by
    # api_name. See the TWO WAYS A FIELD'S VALUE IS STORED note at the top.
    custom_fields: Mapped[dict] = _custom_fields_column()

    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class IdSequence(Base):
    """
    The high-water mark for each collection's reference id.

    Reference ids (ACC-020, CON-016) must NEVER be reused. Deriving the next one
    from max(existing) does reuse them the moment a row is deleted, and the new
    record then inherits every stale reference to the old one — see
    app/ids.py::next_reference_id for the failure this prevents.

    Storing the counter is what makes deletion safe: a DELETE cannot lower a
    value that does not depend on the rows.
    """

    __tablename__ = "id_sequences"

    name = Column(String(40), primary_key=True)
    prefix = Column(String(10), nullable=False)
    pad = Column(Integer, nullable=False, default=3)
    last_value = Column(Integer, nullable=False, default=0)


class Lead(Base):
    """
    A pipeline Lead — Stages 0 through 7. It converts to a Deal at Stage 7 and
    becomes read-only (deals live in a Round-2/3 table not yet built).

    Every lookup here is a real foreign key into a Round-1 table (accounts,
    users, contacts) or into leads itself (parent_pursuit). The four columns
    that will eventually point at Round-3/4/5 tables — partner_deal_registration,
    parent_deal, sap_solution_suite, suite_demonstrated, poc_record,
    poc_brief_gate, ctb_gate — stay plain id columns without a constraint until
    those tables exist; see the Round map in CLAUDE.md.

    ON DELETE SET NULL throughout, never CASCADE: losing the account or user a
    Lead names must not delete the Lead, the same rule contacts.account and
    contacts.engagement_owner already follow.

    contracting_party, days_in_current_stage, days_since_last_update and
    close_date_pushback_count are deliberately NOT columns — they are derived,
    see the properties below and app/schemas.py LeadOut.
    """

    __tablename__ = "leads"

    # ---------------------------------------------------------
    # ID
    # ---------------------------------------------------------

    lead_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    # ---------------------------------------------------------
    # STAGE 0 — CONNECT
    # ---------------------------------------------------------

    opportunity_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    country: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    city_state: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    destination_region: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    booking_region: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    end_client: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_partner_si: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    bd_owner: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    primary_contact: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("contacts.contact_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deal_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    opportunity_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    partner_deal_registration: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    segment: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    theme: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )

    sap_solution_suite: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    project_stage: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    lead_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    probability_pct: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    expected_close_month: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    fx_rate_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )

    estimated_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    is_primary_pursuit: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    parent_pursuit: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("leads.lead_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    parent_deal: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    incremental_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    remarks_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    lighthouse_project: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    gorilla_flag: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    demo_agreed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    demo_scheduled_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    demo_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # ---------------------------------------------------------
    # STAGE 1 — DEMO
    # ---------------------------------------------------------

    demo_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    suite_demonstrated: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    interest_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Register type was "file"; the frontend now renders this as a link (url)
    # field prototype-wide — there is nowhere for an uploaded file to land —
    # see spec/extensions.json fields."leads.data_site_access_confirmation_document".
    # The column itself needs no change: a link fits the same VARCHAR a
    # filename did.
    data_site_access_confirmation_document: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    pilot_commercial_model: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    pilot_fee: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    client_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    competitors_mentioned: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    demo_debrief_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # STAGE 2 — POC / PILOT
    # ---------------------------------------------------------

    poc_record: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    poc_brief_gate: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Free text, PHASE-1 FREEZE (03 Sep 2026): was a multiselect of product
    # ids, backed by the lead_secondary_suites junction table below. Products
    # is a Round-5 table with no frozen fields yet, so there was nothing for
    # the picker to offer. Revert to the junction table once Products ships —
    # frontend/spec/extensions.json leads.secondary_sap_suites carries the
    # matching type_override and the revert note.
    secondary_sap_suites: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ---------------------------------------------------------
    # STAGE 3 — PRESCRIPTION
    # ---------------------------------------------------------

    consultant_specifier: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sales_owner: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    presales_owner: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    client_phase: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    project_team_access_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    budget_estimate: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    budget_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    probable_award_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    pre_bid_alliance_partner: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    alliance_structure: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    pbaa_signed_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    ctb_gate: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    ctb_approval_status: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    ctb_approval_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    total_project_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    # ---------------------------------------------------------
    # HEADER / CURRENT STATE
    # ---------------------------------------------------------

    progression_pct: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    overall_rag: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    next_milestone: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    next_milestone_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True,
    )

    # ---------------------------------------------------------
    # CROSS-CUTTING
    # ---------------------------------------------------------

    stage_skip_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    stage_reversal_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ---------------------------------------------------------
    # SYSTEM
    # ---------------------------------------------------------

    created_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
    )

    modified_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Values for fields created through the Administration Module, keyed by
    # api_name. See the TWO WAYS A FIELD'S VALUE IS STORED note at the top.
    custom_fields: Mapped[dict] = _custom_fields_column()

    demo_attendees = relationship(
        "LeadDemoAttendee",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="LeadDemoAttendee.row_order",
        back_populates="lead",
    )

    feature_gaps = relationship(
        "LeadFeatureGap",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="LeadFeatureGap.row_order",
        back_populates="lead",
    )

    # ---------------------------------------------------------
    # COMPUTED — never columns, always derived (see class docstring)
    # ---------------------------------------------------------

    @property
    def contracting_party(self) -> str | None:
        """
        Partner-sourced deals contract through the partner; everything else
        contracts through the end client. Never entered by hand — see the rule
        in section 4 of the Round 2 spec.
        """
        if self.deal_source == "PARTNER_SOURCED":
            return self.customer_partner_si
        return self.end_client

    @property
    def days_in_current_stage(self) -> int:
        """
        Approximated from modified_date, since the stage_transitions table that
        would record an actual stage-entry timestamp is Round 7 work. Revisit
        once that table exists.
        """
        return (datetime.now(timezone.utc).date() - self.modified_date.date()).days

    @property
    def days_since_last_update(self) -> int:
        return (datetime.now(timezone.utc).date() - self.modified_date.date()).days

    @property
    def close_date_pushback_count(self) -> int:
        """
        Requires a history of expected_close_month edits, which nothing
        persists yet — that belongs to the Round 7 history tables. Always 0
        until then; not a real count.
        """
        return 0


class LeadDemoAttendee(Base):
    """
    leads.demo_attendees — a childlist (spec/extensions.json child_spec,
    inferred), one row per person who attended the Stage 1 demo.

    attendee (contact), organisation (account) and attendee_role are a live
    mirror of the picked Contact via child_field_sync — see
    frontend/src/components/leads/DemoAttendeeSync.ts and ChildListTable.tsx
    for the two directions — but job_title/organisation/attendee_role are
    still real, independently editable columns on the row, not a join: the
    whole point of capturing them here is that they can diverge from the
    Contact record over time (a Stage 1 demo remembers who showed up as they
    were then).

    attendee and organisation carry real foreign keys (contacts, accounts
    both exist since Round 1); ON DELETE SET NULL, same rule every other
    Lead lookup follows — losing the Contact or Account must not delete the
    attendance row.
    """

    __tablename__ = "lead_demo_attendees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("leads.lead_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attendee: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("contacts.contact_id", ondelete="SET NULL"),
        nullable=True,
    )

    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)

    organisation: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
    )

    # contacts__contact_role picklist key.
    attendee_role: Mapped[str | None] = mapped_column(String(40), nullable=True)

    lead = relationship("Lead", back_populates="demo_attendees")


class LeadFeatureGap(Base):
    """
    leads.feature_gaps_logged — a childlist (spec/extensions.json child_spec,
    inferred), one row per capability gap surfaced during the Stage 1 demo.

    suite_module has NO foreign-key constraint yet, same accommodation as
    LeadSecondarySuite.product_id: products is a Round 5 table. Add the
    constraint when that table exists.

    raised_by carries a real foreign key (users exists since Round 1); ON
    DELETE SET NULL, same rule every other Lead lookup follows.
    """

    __tablename__ = "lead_feature_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("leads.lead_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    gap_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    suite_module: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # administration__impact picklist key.
    impact: Mapped[str | None] = mapped_column(String(40), nullable=True)

    raised_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    lead = relationship("Lead", back_populates="feature_gaps")


class Opportunity(Base):
    """
    A pipeline Opportunity — Stages 4 through 6. Born by converting a Lead at
    Stage 3 (ConvertToOpportunityDialog), and converts on to a Deal at Stage 6
    (Round 4/5 table, not yet built).

    WHAT THIS TABLE DOES NOT STORE, DELIBERATELY
    ----------------------------------------------
    spec/module_split.json's `read_through` block names 26 fields — opportunity_
    name, end_client, customer_partner_si, segment, theme, bd_owner, country and
    the rest of a pursuit's identity — that an Opportunity resolves from its
    parent Lead and never stores itself. Carrying them here would be exactly the
    two-places-to-drift bug carry-forward-by-reference exists to prevent. The
    frontend already resolves them client-side (useResolvedRecord fetches
    /api/leads/:id and merges), so no backend work is needed to serve them —
    this table simply has no columns for them.

    Six more fields — total_value_tcv, gross_margin_pct, submitted_on_time,
    licence_discount_pct, total_cost, third_party_pct_of_tcv — are `computed`
    in the register (spec/extensions.json computed_expr, pure formulas over
    other columns on this same table). Computed fields are never stored on any
    module in this build (see FieldControl.tsx's DERIVED set) and there is no
    existing backend convention for evaluating a computed_expr server-side, so
    they are not reproduced here either — a cutover-phase concern, not this one.

    project_stage, probability_pct and lead_status are `own` per module_split —
    each pipeline module keeps its own instance rather than inheriting the
    parent's, the same reasoning Lead's own project_stage/probability_pct/
    lead_status already follow for Stage 0-3.

    Two register api_names are not valid Python identifiers (3rd_party_one_time,
    3rd_party_recurring_per_year — leading digit). Their ORM attributes are
    third_party_one_time / third_party_recurring_per_year, with the real
    register name given as the SQLAlchemy column name via mapped_column's first
    argument — see the matching Pydantic `alias` in schemas.py, which is what
    lets the wire payload still use the register's own key.

    ON DELETE SET NULL throughout for the accounts/users FKs, same rule
    Lead follows. parent_lead is the one exception: it carries NO ondelete
    clause (defaults to RESTRICT) because every identity field on this record
    is read THROUGH it — losing the Lead out from under a converted Opportunity
    would silently blank its entire identity, not just one column, which is a
    materially worse failure than the SET NULL fields risk. The Leads table may
    be empty; the constraint does not require a row to exist yet, only that a
    parent_lead value which IS set must name a real one.
    """

    __tablename__ = "opportunities"

    # ---------------------------------------------------------
    # ID
    # ---------------------------------------------------------

    opportunity_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    # ---------------------------------------------------------
    # RECORD STATE — own instance, never inherited (module_split.json "own")
    # ---------------------------------------------------------

    project_stage: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    probability_pct: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    lead_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # ---------------------------------------------------------
    # ON CONVERSION — set once, at birth
    # ---------------------------------------------------------

    parent_lead: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("leads.lead_id"),
        nullable=True,
        index=True,
    )

    fx_rate_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )

    # ---------------------------------------------------------
    # STAGE 4 — RFP / RFI
    # ---------------------------------------------------------

    rfp_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    rfp_received_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Register type was "file"; rendered as a link (url) field now — see
    # spec/extensions.json fields."leads.rfp_document". Column needs no change.
    rfp_document: Mapped[str | None] = mapped_column(String(255), nullable=True)

    submission_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    arr_annual_recurring: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    one_time_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # See class docstring — leading-digit api_name, python attribute renamed.
    third_party_one_time: Mapped[Decimal | None] = mapped_column(
        "3rd_party_one_time", Numeric(18, 2), nullable=True
    )

    third_party_recurring_per_year: Mapped[Decimal | None] = mapped_column(
        "3rd_party_recurring_per_year", Numeric(18, 2), nullable=True
    )

    contract_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    competitors_noticed: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # bids is a Round 5+ table — plain id column without a constraint yet,
    # same rule Lead's poc_record/ctb_gate/parent_deal already follow.
    bid_record: Mapped[str | None] = mapped_column(String(20), nullable=True)

    bid_submission_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    debrief_requested_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    platform_licence_list_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    services_and_implementation_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    third_party_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Register type was "file"; same link-field change as rfp_document above.
    cost_model_rcm_document: Mapped[str | None] = mapped_column(String(255), nullable=True)

    licence_model: Mapped[str | None] = mapped_column(String(40), nullable=True)

    perpetual_licence_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    client_tender_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # quotes is a Round 5+ table — plain id column, same reasoning as bid_record.
    primary_quote: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Gap-fix fields captured at Stage 4 — spec/extensions.json new_fields.
    nomination_bid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    incumbent_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    value_confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ---------------------------------------------------------
    # STAGE 5 — TECHNICAL EVALUATION
    # ---------------------------------------------------------

    bid_receipt_confirmed_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    first_tbe_received_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    technical_standing: Mapped[str | None] = mapped_column(String(40), nullable=True)

    technical_approval_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    technical_approval_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # ---------------------------------------------------------
    # STAGE 6 — COMMERCIAL EVALUATION
    # ---------------------------------------------------------

    commercial_proposal_submitted_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True
    )

    final_negotiated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    contract_review_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    contract_review_sign_off_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    contract_review_sign_off_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # gates is a Round 6+ table — plain id column, same reasoning as bid_record.
    commercial_gate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    award_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    loi_received_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    agreed_advance_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    agreed_credit_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agreed_liability_cap_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    agreed_ld_cap_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    pay_when_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Gap-fix fields captured at Stage 6 — spec/extensions.json new_fields.
    sow_agreed_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    bidder_declared_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # ---------------------------------------------------------
    # HEADER / CURRENT STATE — own instance, same shape as Lead's
    # ---------------------------------------------------------

    progression_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)

    overall_rag: Mapped[str | None] = mapped_column(String(10), nullable=True)

    next_milestone: Mapped[str | None] = mapped_column(String(200), nullable=True)

    next_milestone_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # ---------------------------------------------------------
    # PRIORITY PICKS — Low Hanging / Top 10 (see app.priority_flags)
    # ---------------------------------------------------------

    is_low_hanging: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    low_hanging_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_top_10: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    top_10_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---------------------------------------------------------
    # CROSS-CUTTING (shared across all three pipeline modules)
    # ---------------------------------------------------------

    stage_skip_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    stage_reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ---------------------------------------------------------
    # SYSTEM (shared across all three pipeline modules)
    # ---------------------------------------------------------

    created_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
    )

    modified_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Values for fields created through the Administration Module, keyed by
    # api_name. See the TWO WAYS A FIELD'S VALUE IS STORED note at the top.
    custom_fields: Mapped[dict] = _custom_fields_column()

    payment_milestones = relationship(
        "OpportunityPaymentMilestone",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OpportunityPaymentMilestone.row_order",
        back_populates="opportunity",
    )


class OpportunityPaymentMilestone(Base):
    """
    opportunities.payment_milestones — a childlist (spec/extensions.json
    child_spec, inferred), so a real child table rather than JSONB: one row per
    milestone, each with its own planned/actual/invoice/payment-received dates
    and status, all independently editable after the row is created.

    Unlike lead_secondary_suites (a pure multiselect junction with no data of
    its own), a milestone row IS data, so it gets a surrogate primary key
    rather than a composite one — nothing about the row shape gives a natural
    key, and "one row per administration__milestone picklist value" is neither
    stated nor enforced anywhere in the register (see the child_spec's own
    note: "Nothing enforces eight rows").

    row_order is display order, set by the caller on write. The register does
    not name a sort column; without one, PostgreSQL row order is unspecified
    and the milestone table would reshuffle itself between saves.

    Four column names carry the register's own em dash (milestone_—_planned_
    date and siblings), which is not a valid Python identifier — same
    accommodation as Opportunity's 3rd_party_* columns: the ORM attribute is
    plain ASCII, the real register name is the SQLAlchemy column name.
    """

    __tablename__ = "opportunity_payment_milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    opportunity_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # administration__milestone picklist key.
    milestone: Mapped[str | None] = mapped_column(String(60), nullable=True)

    pct_of_contract: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    trigger: Mapped[str | None] = mapped_column(String(200), nullable=True)

    milestone_planned_date: Mapped[datetime | None] = mapped_column(
        "milestone_—_planned_date", Date, nullable=True
    )

    milestone_actual_date: Mapped[datetime | None] = mapped_column(
        "milestone_—_actual_date", Date, nullable=True
    )

    milestone_invoice_date: Mapped[datetime | None] = mapped_column(
        "milestone_—_invoice_date", Date, nullable=True
    )

    milestone_payment_received_date: Mapped[datetime | None] = mapped_column(
        "milestone_—_payment_received_date", Date, nullable=True
    )

    # administration__milestone_status picklist key.
    milestone_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    opportunity = relationship("Opportunity", back_populates="payment_milestones")


class Deal(Base):
    """
    A booked order — Stages 7 through 9. Born by converting either an
    Opportunity at Stage 6 (opportunities/ConvertToDealDialog.tsx) or a Lead
    directly at Stage 7 (leads/ConvertToDealDialog.tsx, the POC-1 fast path
    that never created an Opportunity). Both are live conversion paths in the
    frontend today, so a Deal carries TWO independent parent links rather than
    one:

    parent_opportunity
        spec/module_split.json's read_through.parent_link.deals — the identity
        link. fieldsOf('deals') marks opportunity_name, end_client's siblings,
        segment, theme and 20 more as read_through, and src/lib/spec/
        resolveRecord.ts walks EXACTLY this field to resolve them; it has no
        fallback to parent_lead. So a Deal converted from an Opportunity reads
        its identity live through this link, the same way Opportunity.parent_lead
        works — hence the matching ON DELETE behaviour (no ondelete clause;
        losing the Opportunity out from under a converted Deal would silently
        blank its identity, not just one column). NOT a register field: no
        module=deals row in spec/fields.json names it — same as
        Opportunity.parent_lead, which is equally synthetic (no module=
        opportunities row names it either) and is still an ordinary PATCH-able
        scalar; parent_opportunity follows that same precedent rather than
        being special-cased into a create-only field.

    parent_lead
        A real, Mandatory register field (ON CONVERSION, order 3, lookup
        target "lead") — order 3rd on the sheet. This is what leads/
        ConvertToDealDialog.tsx sets when a Lead converts straight to a Deal
        without an intervening Opportunity; that dialog copies the handful of
        identity fields it needs directly onto the payload instead of relying
        on read-through (there is no parent_opportunity to read through in
        that path), so losing the Lead afterward does not blank anything live
        — ON DELETE SET NULL, the same rule every other Deal FK below follows.

    A given Deal has at most one of the two set, depending which path created
    it. This is not a register error to paper over — see the deals.
    linked_expansion_leads entry in spec/extensions.json register_corrections
    for the one related field that WAS removed as stale; parent_lead is not
    in that category, it is simply the other conversion path's link.

    THE SEVEN guarantee_—_* FIELDS ARE NOT COLUMNS HERE
    -----------------------------------------------------
    spec/fields.json lists guarantee_—_type through guarantee_—_status as flat
    scalar rows in ON CONVERSION, same as leads.payment_milestones' four
    milestone_—_* dates were before being read as a child row shape. But
    spec/extensions.json's own note on deals.bid_commitments_register says so
    explicitly: "The guarantee_—_* fields sit flat in ON CONVERSION and are
    read as the row shape" — and src/lib/spec/childSpec.ts's isChildColumnOnly()
    confirms it in code: any field named as a child_spec column is "dropped
    from the form... while the child table goes on rendering it as a column."
    So a bid commitment is a repeating guarantee, one row per instrument, not
    a single guarantee per Deal — see DealBidCommitment below. Confirmed by
    inspection before writing this model, not assumed.

    guarantee_—_pct_of_contract_value is `type: computed`
    (computed_expr "guarantee_—_value / contract_value") and is never stored,
    on any module, in this build — same rule Opportunity's own computed
    fields follow.

    ON DELETE SET NULL throughout for the accounts/users FKs below, same rule
    Lead and Opportunity follow.

    created_by_date / modified_by_date, not created_date/created_by /
    modified_date/modified_by: the Deals sheet genuinely names its system
    timestamps this way (spec/module_split.json shared.equivalence declares
    the pair a known duplicate of the other modules' concept, "NOT silently
    collapsed" — a register_correction, not a rename to apply here). Deals
    also carries no created_by/modified_by lookup at all, so none is added.
    """

    __tablename__ = "deals"

    # ---------------------------------------------------------
    # ID
    # ---------------------------------------------------------

    deal_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # ---------------------------------------------------------
    # ON CONVERSION
    # ---------------------------------------------------------

    deal_name: Mapped[str] = mapped_column(String(200), nullable=False)

    parent_lead: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("leads.lead_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # See class docstring — no ondelete clause (RESTRICT), same rule
    # Opportunity.parent_lead follows, because identity is read through it.
    parent_opportunity: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("opportunities.opportunity_id"),
        nullable=True,
        index=True,
    )

    end_client: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_partner_si: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deal_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)

    delivery_pm: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order_booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    booking_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    erp_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    po_loi_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    project_code: Mapped[str | None] = mapped_column(String(60), nullable=True)

    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    arr_annual_recurring: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    one_time_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Leading-digit register names — same accommodation as Opportunity's own
    # 3rd_party_one_time / 3rd_party_recurring_per_year.
    third_party_one_time: Mapped[Decimal | None] = mapped_column(
        "3rd_party_one_time", Numeric(18, 2), nullable=True
    )

    third_party_recurring_per_year: Mapped[Decimal | None] = mapped_column(
        "3rd_party_recurring_per_year", Numeric(18, 2), nullable=True
    )

    contract_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    psp_completed_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    handover_pack_delivered_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    kickoff_meeting_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    cash_flow_sign_off_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    resource_plan_sign_off_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # bid_commitments_register is below, as a real child table — see class
    # docstring for why the guarantee_—_* register rows are its columns
    # rather than scalars here.

    # ---------------------------------------------------------
    # STAGE 8 — PROJECT SUCCESS
    # ---------------------------------------------------------

    commissioning_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    tandc_sign_off_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    go_live_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    warranty_start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    warranty_end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    contract_completion_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    csat_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)

    csat_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    reference_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Register type was "file"; rendered as a link (url) field prototype-wide,
    # same accommodation as leads.data_site_access_confirmation_document and
    # opportunities.rfp_document.
    reference_document: Mapped[str | None] = mapped_column(String(255), nullable=True)

    re_engagement_30_day_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    re_engagement_90_day_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # expansion_use_cases is below, as a real child table.

    # ---------------------------------------------------------
    # STAGE 9 — EXPANSION & RENEWAL
    # ---------------------------------------------------------

    # Free text, PHASE-1 FREEZE (03 Sep 2026): was a multiselect with NO
    # backing picklist, stored as a junction table of free strings
    # (DealExpansionSuite, same shape lead_secondary_suites followed).
    # Products is a Round-5 table with no frozen fields yet, so there was
    # nothing for the picker to offer. Revert to the junction table once
    # Products ships — frontend/spec/extensions.json deals.expansion_suites
    # carries the matching type_override and the revert note.
    expansion_suites: Mapped[str | None] = mapped_column(String(255), nullable=True)

    incremental_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    contract_expiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    renewal_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    renewal_signed_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # deals.linked_expansion_leads (Mandatory, childlist) was REMOVED from
    # spec/fields.json and spec/extensions.json by hand at review — nothing in
    # the prototype ever populated it (Stage 9 does not create leads), and it
    # named no relationship this build could resolve without inventing one.
    # See the register_corrections entry keyed "deals.linked_expansion_leads"
    # in spec/extensions.json for the criteria.json X9.1 fallout.

    # ---------------------------------------------------------
    # SYSTEM — see class docstring for why this pair, not created_date/
    # created_by/modified_date/modified_by
    # ---------------------------------------------------------

    created_by_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    modified_by_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # NOT a register field — carried for the same reason Lead.active and
    # Opportunity.active are, despite neither being deleted through it either.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Values for fields created through the Administration Module, keyed by
    # api_name. See the TWO WAYS A FIELD'S VALUE IS STORED note at the top.
    custom_fields: Mapped[dict] = _custom_fields_column()

    bid_commitments = relationship(
        "DealBidCommitment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DealBidCommitment.row_order",
        back_populates="deal",
    )

    expansion_use_cases = relationship(
        "DealExpansionUseCase",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DealExpansionUseCase.row_order",
        back_populates="deal",
    )



class DealBidCommitment(Base):
    """
    deals.bid_commitments_register — one row per bid instrument (advance or
    performance bank guarantee), not per generic "commitment": see
    Deal's own docstring for why the register's flat guarantee_—_* fields are
    this row's columns rather than scalars on the Deal itself.

    guarantee_—_pct_of_contract_value is NOT a column: it is `type: computed`
    in the register (computed_expr "guarantee_—_value / contract_value"),
    evaluated once per row from this row's own guarantee_value and the
    parent Deal's contract_value — never stored, same rule every computed
    field in this build follows.
    """

    __tablename__ = "deal_bid_commitments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    deal_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("deals.deal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # deals__guarantee_type picklist key.
    guarantee_type: Mapped[str | None] = mapped_column(
        "guarantee_—_type", String(40), nullable=True
    )

    guarantee_value: Mapped[Decimal | None] = mapped_column(
        "guarantee_—_value", Numeric(18, 2), nullable=True
    )

    guarantee_issue_date: Mapped[datetime | None] = mapped_column(
        "guarantee_—_issue_date", Date, nullable=True
    )

    guarantee_expiry_date: Mapped[datetime | None] = mapped_column(
        "guarantee_—_expiry_date", Date, nullable=True
    )

    guarantee_issuing_bank: Mapped[str | None] = mapped_column(
        "guarantee_—_issuing_bank", String(200), nullable=True
    )

    # deals__guarantee_status picklist key.
    guarantee_status: Mapped[str | None] = mapped_column(
        "guarantee_—_status", String(40), nullable=True
    )

    deal = relationship("Deal", back_populates="bid_commitments")


class DealExpansionUseCase(Base):
    """
    deals.expansion_use_cases — row shape borrowed from the bids_pocs sheet's
    POC USE CASE (children) section, same basis spec/extensions.json states:
    use_case_no, use_case_description, use_case_status (bids_pocs__use_case_
    status picklist) plus estimated_value, which has no register column but
    is what exit criterion X8.3 and deals.incremental_value at Stage 9 need
    to add up.
    """

    __tablename__ = "deal_expansion_use_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    deal_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("deals.deal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    use_case_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    use_case_description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # bids_pocs__use_case_status picklist key.
    use_case_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    deal = relationship("Deal", back_populates="expansion_use_cases")


# =========================================================================
# ROUND 6 — THE METADATA LAYER
# =========================================================================
#
# Everything above this line stores BUSINESS DATA: a lead, an account, a
# guarantee on a deal. Everything below stores the DEFINITION of what a
# business record may contain — the field register itself, as rows.
#
# The direction of truth, and it only runs one way:
#
#     Administration UI -> PostgreSQL -> regenerate -> spec/*.json -> frontend
#
# PostgreSQL is authoritative for editable metadata. spec/fields.json,
# spec/picklists.json and spec/stages.json are GENERATED ARTIFACTS during
# Phase 1, kept because the frontend already consumes them (src/lib/spec/
# index.ts imports them at build time). There is deliberately NO supported
# JSON -> PostgreSQL flow: bootstrap_metadata.py exists once, to get the
# register in here, and after that a hand-edit of a spec file is a local
# change that the next regenerate overwrites. See backend/README.md.
#
# Phase 2 may replace the JSON hop with a metadata API the frontend reads
# directly. Nothing here assumes the JSON layer is permanent.
#
# WHAT THESE TABLES HOLD IS REGISTER SHAPE, NOT SCREEN SHAPE
# -----------------------------------------------------------
# fields.json is the workbook's own shape: ten module sheets, and every
# Stage 0-7 pipeline field filed under `leads`. The three-way pipeline split
# that puts a Stage 5 field on Opportunities is applied by the FRONTEND at
# load time (spec/module_split.json, src/lib/spec/moduleSplit.ts), AFTER the
# JSON is read. So `modules` here holds the register's ten sheets and there
# is no `opportunities` row: reproducing the split in Python would mean two
# implementations of one rule, drifting apart the first time either changed.
# The Administration UI resolves where a field lands using the split the
# frontend already carries — see src/lib/metadata.ts effectiveModuleOf().
#
# DELETION IS LOGICAL, ALWAYS
# ----------------------------
# Deleting a field here marks field_metadata.status = 'deleted' and nothing
# else. It never touches the business table the field's values live in: no
# DROP COLUMN, no UPDATE, no data loss. The column and every value in it
# survive, which is what makes restore real rather than cosmetic — see
# FieldMetadata.status.


class Module(Base):
    """
    One sheet of the field register — `leads`, `accounts`, `bids_pocs`.

    module_key is the natural primary key and carries the register's own
    module string verbatim, because that string is what every field row,
    every sidecar key in spec/extensions.json and every list view already
    names. Anything else would need a translation table to regenerate the
    JSON the frontend reads.

    Ten rows at bootstrap. `opportunities` is NOT one of them — see the
    section comment above.

    Modules are created and deactivated, never deleted: a field row points
    at one, and losing the module would orphan the fields rather than hide
    them, which is the opposite of what deactivation is for.
    """

    __tablename__ = "modules"

    module_key: Mapped[str] = mapped_column(String(60), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # ---------------------------------------------------------
    # PIPELINE STRUCTURE — the part of spec/module_split.json that
    # PostgreSQL now owns. See migration 0005.
    # ---------------------------------------------------------

    # True for Leads, Opportunities and Deals: modules whose records move
    # through stages. Everything else — accounts, contacts, partners — is false
    # and none of the columns below apply to it.
    is_pipeline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # The field this module stores its own stage in. Deals keeps the register's
    # `deal_stage` rather than gaining a second stage field.
    stage_field: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Carry-forward-by-reference: the module an Opportunity or Deal reads its
    # identity fields THROUGH, and the lookup on this record holding that
    # parent's id. Opportunities -> leads via parent_lead; Deals ->
    # opportunities via parent_opportunity.
    parent_module: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("modules.module_key"), nullable=True
    )
    parent_link: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    sections = relationship(
        "Section",
        back_populates="module",
        order_by="Section.sort_order",
        lazy="selectin",
    )


class Section(Base):
    """
    A named group of fields inside one module — `STAGE 0 — CONNECT`,
    `ON CONVERSION`, `CLASSIFICATION`.

    A surrogate primary key rather than (module_key, label): a section can be
    RENAMED from the Administration screen, and a rename must not have to
    rewrite every field row that points at it. The label stays unique within
    its module, which is the invariant the register actually holds — see
    src/lib/spec/index.ts, whose qref (module.section.api_name) is the
    identity of a field and assumes exactly that.

    sort_order is the register's own section order, taken from where each
    section first appears in fields.json. The register has no section sheet
    and no explicit order column; first appearance IS the order, because
    `order` is contiguous per section in every module.
    """

    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("module_key", "label", name="uq_sections_module_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    module_key: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("modules.module_key"),
        nullable=False,
        index=True,
    )

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    module = relationship("Module", back_populates="sections")
    fields = relationship(
        "FieldMetadata",
        back_populates="section",
        order_by="FieldMetadata.sort_order",
    )


class FieldMetadata(Base):
    """
    One row of the field register. 566 of them at bootstrap.

    The columns from `api_name` down to `computed_formula` are EXACTLY the 23
    keys build_spec.py emits into spec/fields.json — see RawFieldSpec in
    src/types/field.ts, whose comment says "Do not add to this interface".
    That correspondence is the whole contract: regenerate_spec.py writes these
    columns straight back out, and the frontend cannot tell a regenerated file
    from a workbook-generated one.

    Two register keys are renamed here and ONLY here, because Python and SQL
    disagree with the register about what a name may be:

        register `type`  -> field_type   (`type` shadows the builtin)
        register `order` -> sort_order   (reserved word in SQL, and the rest
                                          of this schema already says
                                          sort_order for the same idea)

    app/metadata_spec.py::FIELD_JSON_KEYS holds the mapping in one place, so
    the serialiser and the bootstrap cannot drift.

    WHY status, AND WHY IT IS NOT `active`
    ---------------------------------------
    Every other table in this file carries `active`, meaning "in use". This
    one carries `status` ('active' | 'deleted') because the two ideas are
    genuinely different here: an Administration delete is a destructive-looking
    action a user takes deliberately, and it has to be told apart from a field
    that was merely switched off. A deleted field:

      * disappears from the regenerated spec/fields.json, so it vanishes from
        every CRM screen at the next publish;
      * KEEPS its row, its configuration and its deleted_at/deleted_by stamp;
      * leaves the business table completely untouched — the column and every
        value in it survive, which is the point;
      * comes back, configured exactly as it was, on restore.

    Restoring a field is NOT a version rollback. Rollback republishes a whole
    earlier snapshot; restore brings one field back without touching anything
    else. See MetadataVersion.

    WHY `requirement` IS NOT A NOT NULL CONSTRAINT
    -----------------------------------------------
    `requirement` ('Mandatory' | 'Optional' | 'Conditional' | 'System' |
    'Computed' | 'Advisory') is an APPLICATION-level rule: it drives the red
    asterisk and layer 1 of the four-layer transition check
    (src/lib/spec/validation.ts). It deliberately does NOT propagate to the
    business table's nullability. Marking Licence Model required must not make
    an existing half-filled Opportunity unsavable — the same reasoning
    models.Account's docstring already gives for its own nullable columns.

    `extension` mirrors this field's entry in spec/extensions.json, which is
    hand-maintained and NOT generated. It is carried READ-ONLY, so the
    Administration screen can warn that a field has a sidecar computed_expr or
    child_spec behind it; regenerate_spec.py never writes it anywhere. It is
    refreshed only by re-running the bootstrap.
    """

    __tablename__ = "field_metadata"
    __table_args__ = (
        # The register's own identity rule: module.section.api_name is unique
        # (566 rows, zero collisions), while module.api_name is NOT — nine
        # api_names are defined in two sections of one module. Enforcing the
        # qualified form and not the short one is exactly what
        # src/lib/spec/index.ts does.
        #
        # DELETED ROWS ARE INCLUDED. Creating a second `licence_model` in a
        # section that already has a deleted one is refused, and the API says
        # to restore it instead — which is the honest answer, and stops two
        # rows racing to own one column of business data.
        UniqueConstraint(
            "module_key", "section_id", "api_name", name="uq_field_metadata_qref"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    module_key: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("modules.module_key"),
        nullable=False,
        index=True,
    )

    section_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sections.id"),
        nullable=False,
        index=True,
    )

    # ----------------------------------------------------------------
    # THE REGISTER'S OWN 23 COLUMNS — see RawFieldSpec in types/field.ts
    # ----------------------------------------------------------------

    api_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # A real foreign key: every one of the 566 rows that names a picklist
    # names one that exists, so the constraint holds today and stops a typo
    # creating a dropdown with nothing behind it tomorrow. Picklists are
    # deactivated rather than deleted, so it can never break.
    picklist_key: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey("picklists.picklist_key"),
        nullable=True,
        index=True,
    )

    lookup_target: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lookup_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    values_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_any_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    mandatory_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocks_transition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requirement: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str] = mapped_column(String(120), nullable=False)
    # Nullable, unlike its neighbours and unlike RawFieldSpec's `source_ref:
    # string`: four register rows genuinely carry null here (the PROTOTYPE
    # REGISTER EDIT rows added at review, which cite no playbook section). The
    # database has to be able to hold the register as it actually is.
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    use_case: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required_on_skip: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    visibility_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_formula: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ----------------------------------------------------------------
    # ADMINISTRATION STATE — not register columns, never written to JSON
    # ----------------------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="active", server_default="active"
    )

    # WHERE THIS FIELD'S VALUES ARE STORED. 'column' or 'custom_fields'.
    #
    # Explicit, because the alternative is guessing — and the obvious guess,
    # "the API did not recognise this key so it must be a custom field", is
    # exactly how a typo becomes a silently-stored JSON key that nobody ever
    # sees again. The backend reads THIS column and nothing else.
    #
    #   column          a register field with a typed column on its business
    #                   table. All 566 bootstrap rows. Never changes.
    #   custom_fields   created through Administration; its values live in that
    #                   table's custom_fields JSONB, keyed by api_name.
    #
    # It is not derived from `origin` either. `origin` is a register column
    # carrying free text the workbook chose ('Playbook', 'Gap fix'), and using
    # it to decide where data goes would make a documentation string load-
    # bearing. The two happen to agree today; only this one is authoritative.
    storage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom_fields", server_default="column"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Read-only mirror of spec/extensions.json. See the class docstring.
    #
    # none_as_null, because without it a field with no sidecar entry stores the
    # JSON value `null` rather than SQL NULL — which is not the same thing, and
    # makes `WHERE extension IS NOT NULL` answer 566 when the true count is 58.
    extension: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    section = relationship("Section", back_populates="fields")


class Picklist(Base):
    """
    One dropdown — `leads__deal_source`, `segment`.

    picklist_key is the natural primary key: it is the string field_metadata
    names and the key spec/picklists.json is written under, so it has to
    survive a round trip through the JSON unchanged.

    Deactivated, never deleted, because field_metadata.picklist_key is a real
    foreign key into this table.
    """

    __tablename__ = "picklists"

    picklist_key: Mapped[str] = mapped_column(String(120), primary_key=True)

    # Not a register concept — spec/picklists.json is a bare map of key to
    # options. Carried so the Administration list can show a human name beside
    # `bids_pocs__use_case_status`, and never written back to the JSON.
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # The order the picklists are written into picklists.json.
    #
    # A JSON object's key order means nothing to the frontend, which only ever
    # does picklists[key] — so this exists for the DIFF, not for the reader.
    # Sorting the file alphabetically instead moves all 107 picklists and
    # rewrites 2,754 lines the first time anyone publishes, burying the one
    # label that actually changed.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    values = relationship(
        "PicklistValue",
        back_populates="picklist",
        order_by="PicklistValue.sort_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PicklistValue(Base):
    """
    One option of one picklist: the stored KEY, its display label, its sort
    position and whether it is still offered.

    Exactly the four keys spec/picklists.json carries per option (key, label,
    sort, active), so the file regenerates without a shape change.

    `key` is what a record stores — INFRASTRUCTURE, not "Infrastructure" —
    and it is the value already written into every business row, every
    lookup filter and every register condition. Renaming a key would orphan
    stored data silently, so the API refuses it and offers the label instead;
    a value that should no longer be chosen is DEACTIVATED, which hides it
    from new records while every record already holding it still resolves.
    """

    __tablename__ = "picklist_values"
    __table_args__ = (
        UniqueConstraint("picklist_key", "key", name="uq_picklist_values_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    picklist_key: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("picklists.picklist_key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    picklist = relationship("Picklist", back_populates="values")


class Stage(Base):
    """
    One of the ten pipeline stages, 0 to 9.

    `stage` is the natural primary key: the number IS the identity — records
    store it, criteria codes are built from it (E4.1, X3.2), and
    spec/module_split.json's ranges are written in terms of it.

    owner_role is a real foreign key into `roles`, the same table Administration
    already seeds from the administration__roles picklist, so a stage cannot
    name an owner who does not exist.

    A NOTE ON applies_to, WHICH IS ALREADY KNOWN TO BE WRONG
    --------------------------------------------------------
    spec/stages.json says stages 4-7 are 'lead'. spec/module_split.json's own
    $note records that this is a register error and that nothing reads the
    column any more — the pipeline split derives stage ownership from its
    `ranges` block instead. It is carried here verbatim rather than corrected,
    because silently fixing it in the database would close a register gap the
    Spec Health page is deliberately still reporting.
    """

    __tablename__ = "stages"

    stage: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prob_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prob_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner_role: Mapped[str | None] = mapped_column(
        String(30),
        ForeignKey("roles.role_id", ondelete="SET NULL"),
        nullable=True,
    )

    bid_phase: Mapped[str | None] = mapped_column(String(60), nullable=True)
    applies_to: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # WHICH MODULE OWNS THIS STAGE. Leads 0-3, Opportunities 4-6, Deals 7-9.
    #
    # This is what `applies_to` was supposed to say and gets wrong — it still
    # claims stages 4-7 are 'lead'. That value is left exactly as the register
    # wrote it (see the class docstring); this column is the authoritative one,
    # and it is what spec/module_split.json's `ranges` block is now generated
    # from rather than hand-declared.
    owner_module: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("modules.module_key"), nullable=True
    )

    # Display order, which is the stage number today. Carried separately so a
    # future stage inserted between two others can be positioned without
    # renumbering — the number is identity, and renumbering it would repoint
    # every record that stores it.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class MetadataVersion(Base):
    """
    A published snapshot of the whole metadata configuration.

    The six tables above hold ONE state: the live draft, which the
    Administration screens edit directly. This table holds the history — a
    complete, self-contained JSONB copy of the resolved configuration at each
    publish, which is what makes a rollback possible without version-scoping
    every row of every other table.

    IMMUTABLE. Nothing updates or deletes a published row: no endpoint offers
    it, and _guard_immutable() in routers/metadata.py refuses it if one ever
    tries. A rollback does not rewind history, it EXTENDS it — republishing
    version 2 writes a new version 4 whose snapshot is version 2's, with
    restored_from = 2. The record of what was live and when therefore stays
    true, and "we rolled back" is visible rather than inferred from a gap.

    Rollback is NOT the same operation as restoring a deleted field:

        restore     one field, status deleted -> active, nothing else moves
        rollback    the entire configuration returns to an earlier snapshot

    Restoring a field the current draft never had is exactly what a rollback
    would do to every field at once, which is why the two are kept apart.

    `status` is 'published' on every row written today: the draft lives in the
    six tables, not here, so there is nothing to write a draft row for. The
    column exists because a future "prepare a snapshot, publish it later"
    lifecycle would need it, and it is honest about there being one state
    machine rather than two.
    """

    __tablename__ = "metadata_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="published", server_default="published"
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The complete resolved configuration: modules, sections, fields (active
    # ones only, in the shape fields.json carries), picklists and stages.
    # Everything regenerate_spec.py needs, with no join back to the live
    # tables — that independence is what lets an old version still be
    # republished after the draft has moved on.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # The version_no this one re-published, when it was created by a rollback.
    restored_from: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    published_by: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# =========================================================================
# THE FIELD PLACEMENT MODEL  (Round 7)
# =========================================================================
#
# Replaces field_metadata, which had one column — module_key — doing three
# unrelated jobs: it was the uniqueness scope, the provenance stamp AND the
# answer to "which screen shows this field". Only the third is what an
# administrator means by "module", and it was the one meaning the column did
# not carry: the register files the whole Stage 0-7 pipeline on the `leads`
# sheet, so Administration -> Opportunities -> Fields listed ZERO of the 105
# fields an Opportunity actually renders.
#
# The three jobs are now three columns with three names:
#
#     field_definitions.scope_key      the uniqueness scope
#     field_definitions.origin_module  provenance, read by nothing
#     field_placements.module_key      where the user sees it   <- the answer
#
# WHAT LIVES WHERE
# ----------------
#     field_definitions   what the field IS.   One row per concept.
#     field_placements    where it APPEARS and how its VALUE behaves.
#                         One row per (definition, module).
#
# There is deliberately no third `value_rules` table. Value behaviour is always
# a property of the destination — "I hold my own", "I read through my parent",
# "I was seeded from my parent" — and the source is never chosen: it is the
# nearest ancestor with value_mode='own', walked through modules.parent_module,
# which this schema already holds. A field+source+destination table would store
# three rows for what is one fact per placement and add a surface on which the
# pair table and the parent chain can contradict each other.


# The three value modes. Six `carry` values collapse into these, because two of
# the six were duplicates of one another and three were provenance:
#
#   own            This module stores the value in its own table. Absorbs the
#                  old `own`, `own_instance`, `shared` and `moved`. `shared`
#                  and `own_instance` were behaviourally identical — both give
#                  each module an independent value — and differed only in
#                  which section the copy landed in, which is section_id's job.
#
#   read_through   This module stores NOTHING. The value is resolved from the
#                  parent record every time it is read, so the same End Client
#                  cannot exist in three places and drift.
#
#   carry_forward  The value is COPIED from the parent once, when this record
#                  is created, and this module owns it from then on. Distinct
#                  from `own` (which starts empty) and from `read_through`
#                  (which never stores). Whether it may then diverge is
#                  value_locked.
VALUE_MODES = ("own", "read_through", "carry_forward")

# Where a placement's values are kept on ITS module's business table. Null for
# read_through, which keeps none. On the placement rather than the definition
# because it describes one table, and each module has its own.
STORAGE_MODES = ("column", "custom_fields")

# Where an anchored placement draws relative to its anchor.
#
#   after    a new row directly beneath the anchor, sharing its grid cell. What
#            a conditional field wants: the reason box opens under the question
#            that revealed it, not somewhere else on the same row.
#   beside   the adjacent grid cell — the placement is spliced into the
#            section's flat field list immediately after the anchor.
ANCHOR_POSITIONS = ("after", "beside")

# How much of the two-column form grid a placement takes. Null means "whatever
# this field type takes on its own" — see FULL_WIDTH in FieldRow.tsx — which is
# what every placement carried before anchors existed.
LAYOUT_SPANS = ("full", "half")


class FieldDefinition(Base):
    """
    One canonical field. The answer to "what IS this field".

    EXACTLY ONE ROW PER CONCEPT. `One-Time Revenue` is one row, not one per
    module — the register had it as two (a `leads` row captured at Stage 4 and
    a `deals` row captured at Stage 7) with nothing in the schema saying they
    were the same thing, so renaming one renamed Opportunities and left Deals
    alone. 17 such rows collapsed into 13 concepts at migration.

    WHY scope_key, AND WHY NOT A BARE UNIQUE(api_name)
    ---------------------------------------------------
    api_name is not globally unique and must not be forced to be:
    `accounts.name` and `contacts.name` are different fields that happen to
    share a word. Uniqueness needs a scope, and the scope is:

        'pipeline'            leads + opportunities + deals share one namespace,
                              which is what makes One-Time Revenue ONE row
        '<module>'            every other module is its own namespace
        '<module>__<child>'   a child entity inside a module

    The last one exists because ten api_names are defined twice inside one
    module today — `bids_pocs.status` three times. Every one of them is a child
    ENTITY wearing a section's clothes (`GATE CHECKLIST ITEM`, `TBE QUERY`,
    `DEPLOYMENT SIZE`), so the collisions are real data, not errors, and the
    uniqueness constraint has to be expressible over them. That the register
    models child entities as sections is pre-existing debt; scope_key makes it
    survivable without pretending it is fixed.

    WHAT IS *NOT* HERE
    ------------------
    Twelve columns that used to sit on field_metadata moved to the placement,
    because measurement showed they already vary by module: section, order,
    capture_stage, mandatory_from, blocks_transition, requirement,
    required_on_skip, visibility_condition, condition, storage — and module_key
    itself. `one_time_revenue` is in `STAGE 4 — RFP / RFI` on Opportunities and
    in `ON CONVERSION` on Deals; there is no one section it could have.
    """

    __tablename__ = "field_definitions"
    __table_args__ = (
        # THE GUARANTEE. One canonical definition per concept per scope.
        #
        # DELETED ROWS INCLUDED, exactly as field_metadata's own qref
        # constraint included them: creating a second `licence_model` in a
        # scope that already has a deleted one is refused, and the API says to
        # restore it instead. That is the honest answer, and it stops two rows
        # racing to own one column of business data.
        UniqueConstraint("scope_key", "api_name", name="uq_field_definitions_scope"),
        # Not a constraint anybody queries — it is the target of the placement's
        # composite foreign key, which is what keeps the denormalised
        # field_placements.api_name from ever drifting from this row.
        UniqueConstraint("id", "api_name", name="uq_field_definitions_id_api_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scope_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Machine identity. IMMUTABLE — it is the key every record, every condition,
    # every formula and every custom_fields JSONB entry is written under, so a
    # rename would orphan stored data while looking like it worked. The API
    # refuses it and offers the label instead, the same rule PicklistValue.key
    # already states for option keys.
    api_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # The default display name, and the answer to "rename it once, everywhere".
    # A module that needs a different word uses field_placements.label_override.
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- the shape of the value: identical on every placement, or the same
    # ---- concept would mean `currency` on one screen and `date` on another
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    picklist_key: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("picklists.picklist_key"), nullable=True, index=True
    )
    lookup_target: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lookup_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_formula: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- documentation. One concept, one explanation.
    values_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    use_case: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ---- provenance. Absorbs the whole meaning of the old `new` carry value.
    origin: Mapped[str] = mapped_column(String(120), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Where the CONCEPT was first defined. Audit only, and named so that nobody
    # mistakes it for placement: it is the single surviving fragment of the old
    # module_key's meaning, and it MUST NOT be used to decide what Administration
    # shows. That question is answered by field_placements.module_key.
    origin_module: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("modules.module_key"), nullable=True
    )

    # Logical delete of the whole concept, unchanged in meaning from
    # field_metadata.status: the row stays, the business columns and every value
    # in them survive, and restore is real. Never a DROP COLUMN.
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="active", server_default="active"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )

    # Read-only mirror of this field's spec/extensions.json entry. Carried so
    # Administration can warn that a sidecar computed_expr or child_spec sits
    # behind a field; never written back anywhere.
    extension: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # primaryjoin is explicit because there are TWO foreign key paths back to
    # this table: the plain definition_id, and the composite
    # (definition_id, api_name) that keeps the denormalised api_name honest.
    # Both are wanted; the ORM just has to be told which one is the join.
    placements = relationship(
        "FieldPlacement",
        back_populates="definition",
        primaryjoin="FieldDefinition.id == foreign(FieldPlacement.definition_id)",
        order_by="FieldPlacement.module_key",
        lazy="selectin",
    )


class FieldPlacement(Base):
    """
    One appearance of one field on one module. The answer to "where does the
    user see this, and how does its value behave here".

    THIS IS THE COLUMN ADMINISTRATION FILTERS ON. `Administration ->
    Opportunities -> Fields` is now literally

        SELECT ... FROM field_placements WHERE module_key = 'opportunities'

    and it returns the same 105 rows the CRM renders, because the CRM's field
    list is generated from these rows too. The two cannot drift, because
    there is only one table for them to drift from.

    WHAT REPLACED WHAT
    ------------------
    Everything spec/module_split.json used to decide at load time is a row
    here. `own`, `shared`, `read_through`, `reassign`, `relocated_fields` and
    `section_order` do not survive as mechanisms — a relocated field simply
    has the capture_stage and the section it actually has, and there is
    nothing to override. See app/metadata_resolver.py.
    """

    __tablename__ = "field_placements"
    __table_args__ = (
        # One definition appears at most once on one module/shape. There is
        # exactly one "One-Time Revenue on Deals".
        UniqueConstraint(
            "definition_id", "module_key", "scope_key", name="uq_field_placements_one"
        ),
        # TWO DIFFERENT definitions may not collide on one record shape. A
        # record keys on api_name alone, so two would overwrite each other.
        #
        # This is precisely the containment assertion src/lib/spec/moduleSplit.ts
        # performed at load time, moved into the database where it cannot be
        # skipped, cannot be reached only on a code path nobody runs, and
        # applies to admin-created fields as well as register ones.
        UniqueConstraint(
            "module_key", "scope_key", "api_name", name="uq_field_placements_qname"
        ),
        # The denormalised api_name is held honest by the definition it points
        # at, so it can never drift into naming something the definition does
        # not. It is denormalised only because the constraint above cannot be
        # written across a join.
        ForeignKeyConstraint(
            ["definition_id", "api_name"],
            ["field_definitions.id", "field_definitions.api_name"],
            name="fk_field_placements_definition_api_name",
        ),
        # A read-through placement stores nothing and is not editable. Without
        # this a row could claim to read through its parent AND keep its own
        # copy, which is the two-places-to-drift bug the mode exists to prevent.
        CheckConstraint(
            "value_mode <> 'read_through' OR (editable = false AND storage IS NULL)",
            name="ck_field_placements_read_through",
        ),
        # Every mode except read_through must say where its values live.
        CheckConstraint(
            "value_mode = 'read_through' OR storage IS NOT NULL",
            name="ck_field_placements_storage_required",
        ),
        CheckConstraint(
            "value_mode IN ('own', 'read_through', 'carry_forward')",
            name="ck_field_placements_value_mode",
        ),
        CheckConstraint(
            "storage IS NULL OR storage IN ('column', 'custom_fields')",
            name="ck_field_placements_storage",
        ),
        # value_locked is meaningless unless a value was carried in the first
        # place. An `own` field is not "unlocked" — nothing locked it.
        CheckConstraint(
            "value_locked = false OR value_mode = 'carry_forward'",
            name="ck_field_placements_value_locked",
        ),
        # ---- ANCHORS. See the columns below and 0013_field_anchors.py.
        # An anchor with no position, or a position anchored to nothing, is
        # half a placement decision.
        CheckConstraint(
            "(anchor_field IS NULL) = (anchor_position IS NULL)",
            name="ck_field_placements_anchor_pair",
        ),
        CheckConstraint(
            "anchor_position IS NULL OR anchor_position IN ('after', 'beside')",
            name="ck_field_placements_anchor_position",
        ),
        # The one cycle a CHECK can see. Longer loops are walked in
        # routers/metadata.py, which is also where "the anchor exists and is
        # active on this module" lives — see the migration for why neither is
        # a foreign key.
        CheckConstraint(
            "anchor_field IS NULL OR anchor_field <> api_name",
            name="ck_field_placements_anchor_self",
        ),
        CheckConstraint(
            "layout_span IS NULL OR layout_span IN ('full', 'half')",
            name="ck_field_placements_layout_span",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    definition_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("field_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Denormalised from the definition — see the composite FK above.
    api_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # WHERE THE USER SEES THIS FIELD. The whole point of the redesign.
    module_key: Mapped[str] = mapped_column(
        String(60), ForeignKey("modules.module_key"), nullable=False, index=True
    )

    # The record shape inside that module — the module itself for an ordinary
    # field, or a child entity for one of the ten collisions described on
    # FieldDefinition. Mirrors the definition's scope only when the definition
    # is not in the shared 'pipeline' scope, which is why it is stored rather
    # than joined: a pipeline definition places on three different modules and
    # the placement's shape is the module, not 'pipeline'.
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id"), nullable=False, index=True
    )

    # Position within the section, on THIS module's form. Replaces the
    # per-module renumbering loop moduleSplit.ts ran at load time.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # This module's word for the field, when it needs a different one. NULL
    # means "use the definition's label", which is the case for all but five
    # placements. Exactly the old module_split.json `relabel` block: the
    # register calls project_stage "Lead Stage", which is simply the wrong
    # word on an Opportunity.
    label_override: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ---- stage gating, per module. It genuinely differs: one_time_revenue is
    # ---- captured at Stage 4 on Opportunities and at Stage 7 on Deals, and
    # ---- incremental_value is Mandatory on one module and Conditional on the
    # ---- other. This is also where the old `relocated_fields` override
    # ---- mechanism went: a relocated field just has the stage it has.
    capture_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_any_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    mandatory_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocks_transition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requirement: Mapped[str] = mapped_column(String(20), nullable=False)
    required_on_skip: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Conditions name sibling fields, and the sibling set differs per module —
    # a condition naming a field this module does not have cannot compile.
    visibility_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- the value layer. See VALUE_MODES above.
    value_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="own", server_default="own"
    )
    # May a carried value diverge from its source afterwards? A boolean rather
    # than a fourth mode, because it is meaningless for the other two — see the
    # check constraint. false = the Deal may renegotiate what it was handed.
    value_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Read-only on this module. Forced false for read_through by constraint;
    # currently inferred from `carry` in three separate frontend places.
    editable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # NULL for read_through, which stores nothing. See STORAGE_MODES.
    storage: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ---- logical delete, from THIS module only
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="active", server_default="active"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    # Was this taken down by a definition-level delete, or removed from this
    # module on its own? Restore depends on the difference: reactivating a
    # definition must bring back the placements ITS deletion killed, and must
    # NOT resurrect one an admin had deliberately removed a month earlier.
    deleted_by_cascade: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # How this row was derived at migration — 'register', 'reassigned_by_stage',
    # 'shared_section', 'own_instance', 'read_through', 'new_fields', 'admin'.
    # Audit only, read by nothing at runtime. Without it a lossless migration
    # cannot be proved after the fact, and the old `moved` / `new` carry values
    # would lose the one thing about them that was worth keeping.
    provenance: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ---- WHERE THIS FIELD DRAWS, as against what kind of field it is.
    #
    # section_id answers "what kind of field is this" — CROSS-CUTTING, SYSTEM,
    # RECORD STATE. anchor_field answers "where does it go". Those were one
    # value until now, which is why On Hold Reason sat fifty-five rows and one
    # tab away from the Lead Status that asks for it.
    #
    # NULL is the ordinary case and the default: draw in my own section's list,
    # in sort_order. A non-NULL anchor names another api_name ON THIS MODULE,
    # and the field renders next to it wherever that field happens to be —
    # including in a section this placement does not belong to. The register
    # keeps its category; the form gets the position.
    #
    # A conditional field MUST be anchored to its trigger to work at all: the
    # visibility_condition is evaluated against live form state, so the trigger
    # and the field it reveals have to be inside the same RecordForm or the
    # reveal cannot happen until after a save.
    anchor_field: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # 'after'  — a new row directly beneath the anchor, in the same grid cell.
    # 'beside' — the adjacent grid cell, i.e. spliced into the section's flat
    #            field list immediately after the anchor.
    anchor_position: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # 'full' spans both columns of the form grid, 'half' takes one. NULL means
    # "whatever this field type takes on its own", which is what every row
    # carried before anchors existed and what FieldRow's FULL_WIDTH set decides.
    layout_span: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    definition = relationship(
        "FieldDefinition",
        back_populates="placements",
        primaryjoin="FieldDefinition.id == foreign(FieldPlacement.definition_id)",
    )
    section = relationship("Section")


# =========================================================================
# ROUND 7 — audit-log-shaped tables
# =========================================================================
#
# Three tables, none of them register data: they record what happened to a
# leads/opportunities/deals/accounts/contacts row, not what the row itself
# contains. `record_id` (and, on Conversion, `source_id`/`target_id`) is a
# plain string column rather than a foreign key on all three, because the
# module column says which of several tables it names — one FK cannot point
# at five different parents. See app/audit.py and routers/transitions.py,
# routers/conversions.py.


class StageTransition(Base):
    """
    One recorded pipeline stage move. CLAUDE.md: "Stages are states, not
    steps" — a skip forward or a move backward is legal, provided it carries
    a reason, and this table is the only place that reason is kept. Written
    by AdvanceStageDialog.tsx (opportunities, deals), LeadAdvanceDialog.tsx
    (leads, including its cross into Opportunities) and DealDetailPage.tsx's
    expansion-lead creation — see lib/pipeline.ts's Transition interface,
    which this table's columns mirror exactly.

    Lead.days_in_current_stage (models.py) has approximated its answer from
    modified_date because this table did not exist yet; its docstring flags
    the exact line to revisit now that it does. Not changed here — recomputing
    it from real stage-entry timestamps is a separate piece of work.
    """

    __tablename__ = "stage_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    module: Mapped[str] = mapped_column(String(20), nullable=False)
    record_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    from_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    to_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    is_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_reversal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    actor: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Conversion(Base):
    """
    One record of a Lead becoming an Opportunity or Deal, or an Opportunity
    becoming a Deal — the audit trail ConvertToOpportunityDialog.tsx,
    LeadAdvanceDialog.tsx and opportunities/ConvertToDealDialog.tsx already
    post to today, against the browser store. copied_fields is the list of
    api_names carried into the new record, not their values — the new record
    itself is that.
    """

    __tablename__ = "conversions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    source_module: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_module: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    copied_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    actor: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    """
    A record-level CRUD trail: who created, edited or deleted which row of
    leads/opportunities/deals/accounts/contacts, and when. Written from
    inside those routers' own create/patch/put/delete handlers (app/audit.py
    ::record_audit), never from a public POST endpoint — a client cannot
    write its own audit trail.

    Deliberately distinct from two things it could be confused with:
    * the (browser-only, MSW) automation log, which lists SIMULATED system
      events, not real CRUD;
    * metadata_versions, which is Round 6's history of the FIELD REGISTER
      itself, not of any lead/account/opportunity/deal/contact row.

    changed_fields is the list of api_names the write touched, not a
    before/after diff — enough to answer "was X edited and by whom", which is
    what a prototype audit trail needs; capturing old values too would mean
    reading every row twice on every write for a value nothing here uses yet.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    record_module: Mapped[str] = mapped_column(String(20), nullable=False)
    record_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # created | updated | deleted

    changed_fields: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    actor: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


# =========================================================================
# ROUND 3 — deal registration
# =========================================================================
#
# Unlike every module above, `registrations` and `conflicts` have no sheet of
# their own in the field register: the workbook describes both under the
# `partners` module, in its DEAL REGISTRATION and CONFLICT ADJUDICATION
# sections respectively (see spec/extensions.json's `registrations.$note` and
# MODULE_OF_COLLECTION in src/lib/spec/index.ts). The two tables below are
# real, ordinary business tables all the same — editable records with their
# own reference id, not audit-log rows — so they follow the accounts.py /
# contacts.py shape (custom_fields JSONB, a real primary key that IS the
# reference id), not the Round 7 audit tables' shape.


class DealRegistration(Base):
    """
    A partner's claim to a deal, and the exclusivity window Astrikos may grant
    it — Partner Playbook §6.2. See src/lib/partners.ts, which derives the
    live state (active/expiring/expired/superseded/rejected) from these dates
    rather than trusting registration_status alone; that derivation is
    unchanged by this table's existence.

    All three lookups are SET NULL on delete, same as Lead.end_client and
    Contact.account: `Mandatory` in the register is a form-engine rule here
    too, not a storage constraint — see the trade explained at the top of
    this file.
    """

    __tablename__ = "deal_registrations"

    registration_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    partner: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("accounts.account_id", ondelete="SET NULL"), nullable=True
    )
    end_client: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("accounts.account_id", ondelete="SET NULL"), nullable=True
    )
    project_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    expected_timeline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    partner_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    acknowledged_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Computed client-side (lib/partners.ts::acknowledgementPatch/registrationState)
    # and PUT as a literal value on write, same convention as
    # Lead/Opportunity's fx_rate_at_entry — nothing here recomputes it.
    acknowledgement_sla_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    exclusivity_start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    exclusivity_expiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    registration_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    extension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    linked_lead: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("leads.lead_id", ondelete="SET NULL"), nullable=True
    )

    custom_fields: Mapped[dict] = _custom_fields_column()


class RegistrationConflict(Base):
    """
    One adjudication between a colliding pair of DealRegistrations — Partner
    Playbook §6.2's CONFLICT ADJUDICATION section. A record of its own, not a
    patch on either registration: registration_a/registration_b are stamped
    from the collision that raised it (see ConflictPanel.tsx), never typed.

    Detection of a collision is computed client-side
    (lib/partners.ts::collidingRegistrations) and creates nothing by itself;
    this row only exists once a person has actually filled the adjudication
    form. Whether a decision automatically supersedes the losing registration
    is deliberately NOT handled here — ConflictPanel.tsx still offers "Mark
    Superseded" as its own explicit PUT to deal_registrations, exactly as it
    did against the browser store.
    """

    __tablename__ = "registration_conflicts"

    conflict_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    registration_a: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("deal_registrations.registration_id", ondelete="SET NULL"), nullable=True
    )
    registration_b: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("deal_registrations.registration_id", ondelete="SET NULL"), nullable=True
    )

    who_registered_first: Mapped[str | None] = mapped_column(String(300), nullable=True)
    stronger_client_relationship: Mapped[str | None] = mapped_column(String(300), nullable=True)
    better_delivery_capability: Mapped[str | None] = mapped_column(String(300), nullable=True)

    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    both_partners_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    custom_fields: Mapped[dict] = _custom_fields_column()

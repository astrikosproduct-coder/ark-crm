"""Pursuit Groups, one revenue source per module, and a Deal Status that saves

Revision ID: 0020_pursuit_groups
Revises: 0019_fx_rate_free_text
Create Date: 2026-09-13

THE PROBLEM
-----------
Partner-A and Partner-B bring the same project at the same End Client. Astrikos
chooses to pursue both rather than adjudicate, so there are two leads for one
piece of revenue — and Playbook §7.2 says only the primary pursuit may roll up.
The register already had the vocabulary (leads.is_primary_pursuit,
leads.parent_pursuit) and nothing used it. Nothing could: a flag on the lead
stays behind when the lead converts, and the lead is read-only from then on.

WHAT THIS ADDS
--------------
pursuit_groups
    One row per project chased through more than one partner. It holds WHICH
    pursuit is primary, so changing the primary never writes a converted,
    read-only record. A pursuit is a chain Lead -> Opportunity -> Deal and is
    named by its first record's id (primary_pursuit). A record with no group is
    the primary of a group of one — no row is written for it.

leads/opportunities/deals.pursuit_group
    Membership. Copied down a conversion by the server, never by the client.

opportunities/deals.is_primary_pursuit
    A server-written copy of "is this chain the group's primary", so a list can
    filter on it. leads already had the column.

leads.not_duplicate_reason
    The answer given when "EC already has an open pursuit — join its group?"
    is declined. Declining without one is refused.

registration_conflicts.primary_registration
    Which registration is primary when the decision is "Both pursued".

deals.lead_status
    Deal Status. The Deals register has carried an active, storage='column'
    placement for it since Round 6, labelled "Deal Status", with no column
    behind it — so choosing Closed Lost on a Deal saved without error and came
    back empty. models.Deal called that deliberate because nothing read it.
    Pipeline totals and the pursuit-group close rule read it now.

fx_rate_at_entry: text -> numeric(12,6), on leads and opportunities
    REVERSES 0019, deliberately. 0019 made the rate free text so a BD could
    write where it came from; nothing computed with it then. Pipeline totals
    are reported in USD now, and a sentence cannot be divided by. The rate is
    LOCAL CURRENCY UNITS PER 1 USD (AED 3.6725), so USD = local / rate.

    NOT LOSSY, AND REFUSES RATHER THAN GUESS. 0019's downgrade stripped
    non-digits and nulled what was left over; this upgrade does not. Any row
    whose text is not a plain number stops the migration and is listed, so the
    person running it decides what "3.67 (ADCB spot)" was meant to be.

THIS IS NOT ADMINISTRATION ISSUING DDL — see 0014's docstring. Register rows for
the new fields are written by pursuit_group_metadata.py, and the fx definition
change is made here, with its column, for the reason 0019 gave: changing only
one half leaves the register promising a type the column rejects.
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_pursuit_groups"
down_revision = "0019_fx_rate_free_text"
branch_labels = None
depends_on = None

PIPELINE_TABLES = ("leads", "opportunities", "deals")
FX_TABLES = ("leads", "opportunities")
FX = "fx_rate_at_entry"

#: A plain decimal, optionally padded. Anything else is refused, not coerced.
NUMBER = r"^\s*[0-9]+(\.[0-9]+)?\s*$"


def _create_pursuit_groups() -> None:
    op.create_table(
        "pursuit_groups",
        sa.Column("group_id", sa.String(20), primary_key=True),
        sa.Column(
            "end_client",
            sa.String(20),
            sa.ForeignKey("accounts.account_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # No foreign key: a pursuit is named by its first record, which is a
        # LEAD-… for almost every chain and an OPP-… for an Opportunity created
        # without a Lead. One column cannot reference two tables.
        sa.Column("primary_pursuit", sa.String(20), nullable=True),
        sa.Column(
            "primary_registration",
            sa.String(20),
            sa.ForeignKey("deal_registrations.registration_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_conflict",
            sa.String(20),
            sa.ForeignKey("registration_conflicts.conflict_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_by",
            sa.String(20),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "modified_by",
            sa.String(20),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------ fx: refuse before altering
    unparseable = []
    for table in FX_TABLES:
        key = "lead_id" if table == "leads" else "opportunity_id"
        rows = conn.execute(
            sa.text(
                f"SELECT {key}, {FX} FROM {table} "
                f"WHERE {FX} IS NOT NULL AND btrim({FX}) <> '' AND {FX} !~ :pattern"
            ),
            {"pattern": NUMBER},
        ).all()
        unparseable += [f"{table}.{row[0]} = {row[1]!r}" for row in rows]
    if unparseable:
        raise RuntimeError(
            "0020 stopped: these FX rates are not plain numbers, and the column "
            "is becoming numeric (local units per 1 USD). Correct them, then "
            "re-run:\n  " + "\n  ".join(unparseable)
        )

    for table in FX_TABLES:
        op.alter_column(
            table,
            FX,
            type_=sa.Numeric(12, 6),
            existing_type=sa.Text(),
            existing_nullable=True,
            postgresql_using=f"NULLIF(btrim({FX}), '')::numeric",
        )

    conn.execute(
        sa.text(
            "UPDATE field_definitions SET field_type = 'number', max_length = NULL, "
            "label = 'FX Rate (local per 1 USD)', "
            "values_note = 'Local currency units per 1 USD, e.g. 3.6725 for AED. USD = local value / rate.' "
            "WHERE api_name = :name"
        ),
        {"name": FX},
    )

    # ------------------------------------------------------------ pursuit groups
    # app/main.py runs Base.metadata.create_all on startup, so a dev server that
    # reloaded after models.py gained PursuitGroup has already created this
    # table — empty, and with exactly the model's shape. Accepted rather than
    # failed on; a table holding rows here would be something else, and is.
    if sa.inspect(conn).has_table("pursuit_groups"):
        count = conn.execute(sa.text("SELECT count(*) FROM pursuit_groups")).scalar()
        if count:
            raise RuntimeError(f"0020 stopped: pursuit_groups already exists and holds {count} row(s)")
    else:
        _create_pursuit_groups()

    for table in PIPELINE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "pursuit_group",
                sa.String(20),
                sa.ForeignKey("pursuit_groups.group_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_pursuit_group", table, ["pursuit_group"])

    for table in ("opportunities", "deals"):
        op.add_column(
            table,
            sa.Column(
                "is_primary_pursuit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    op.add_column("leads", sa.Column("not_duplicate_reason", sa.Text(), nullable=True))

    op.add_column(
        "registration_conflicts",
        sa.Column(
            "primary_registration",
            sa.String(20),
            sa.ForeignKey("deal_registrations.registration_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.add_column("deals", sa.Column("lead_status", sa.String(30), nullable=True))
    # Every existing Deal is open: nothing could ever have saved it otherwise.
    conn.execute(sa.text("UPDATE deals SET lead_status = 'OPEN' WHERE lead_status IS NULL"))

    # --------------------------------------------- existing parent_pursuit links
    # A lead already pointing at a parent pursuit is a two-member group. The
    # live database had none on 13 Sep 2026; this is here so the migration is
    # right on any copy that does, rather than silently leaving the link behind.
    pairs = conn.execute(
        sa.text(
            "SELECT l.lead_id, l.parent_pursuit, p.end_client FROM leads l "
            "JOIN leads p ON p.lead_id = l.parent_pursuit "
            "WHERE l.parent_pursuit IS NOT NULL"
        )
    ).all()
    groups: dict[str, str] = {}
    for lead_id, parent_id, end_client in pairs:
        group_id = groups.get(parent_id)
        if group_id is None:
            group_id = f"PG-{len(groups) + 1:04d}"
            groups[parent_id] = group_id
            conn.execute(
                sa.text(
                    "INSERT INTO pursuit_groups (group_id, end_client, primary_pursuit, "
                    "created_date, modified_date) VALUES (:g, :e, :p, now(), now())"
                ),
                {"g": group_id, "e": end_client, "p": parent_id},
            )
            conn.execute(
                sa.text("UPDATE leads SET pursuit_group = :g, is_primary_pursuit = true WHERE lead_id = :p"),
                {"g": group_id, "p": parent_id},
            )
        conn.execute(
            sa.text("UPDATE leads SET pursuit_group = :g, is_primary_pursuit = false WHERE lead_id = :l"),
            {"g": group_id, "l": lead_id},
        )
    if groups:
        conn.execute(
            sa.text(
                "INSERT INTO id_sequences (name, prefix, pad, last_value) "
                "VALUES ('pursuit_groups', 'PG', 4, :n)"
            ),
            {"n": len(groups)},
        )
    print(f"  [0020] {len(groups)} pursuit group(s) created from existing parent_pursuit links")
    print("  [0020] now run:  python pursuit_group_metadata.py --apply && python regenerate_spec.py --apply")


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_column("deals", "lead_status")
    op.drop_column("registration_conflicts", "primary_registration")
    op.drop_column("leads", "not_duplicate_reason")
    for table in ("opportunities", "deals"):
        op.drop_column(table, "is_primary_pursuit")
    for table in PIPELINE_TABLES:
        op.drop_index(f"ix_{table}_pursuit_group", table_name=table)
        op.drop_column(table, "pursuit_group")
    op.drop_table("pursuit_groups")
    conn.execute(sa.text("DELETE FROM id_sequences WHERE name = 'pursuit_groups'"))

    # numeric -> text is lossless; 0019's own shape is restored exactly.
    for table in FX_TABLES:
        op.alter_column(
            table,
            FX,
            type_=sa.Text(),
            existing_type=sa.Numeric(12, 6),
            existing_nullable=True,
            postgresql_using=f"{FX}::text",
        )
    conn.execute(
        sa.text(
            "UPDATE field_definitions SET field_type = 'text', max_length = 100, "
            "label = 'FX Rate at Entry', values_note = 'Rate to USD' WHERE api_name = :name"
        ),
        {"name": FX},
    )

"""
Pursuit Groups — one project at one End Client, pursued through more than one
partner, of which exactly one pursuit counts. See models.PursuitGroup.

EVERY RULE IS HERE. The routers call in; nothing else writes pursuit_group or
is_primary_pursuit. A rule enforced in a dialog is a rule the next client does
not know about.

    guard_possible_duplicate  a Lead for an End Client with another open pursuit
                              must join its group or say why not (422)
    auto_join_from_conflict   a Lead whose registration sits in a "Both pursued"
                              conflict joins that conflict's group
    inherit_on_create         an Opportunity or Deal takes its parent's group
    guard_close               the primary may not go Closed Lost while a
                              secondary is still open (409)
    guard_win                 a secondary may not become a Deal (409)
    guard_end_client_change   a grouped record may not change End Client (409)

A PURSUIT is a chain Lead -> Opportunity -> Deal named by its first record's id.
The live end of the chain — the record not yet converted — is the one whose
stage, status and value describe the pursuit.

NOTHING HERE IS ROLE-BOUND. Any signed-in user with a role may change the
primary, remove a member or decide "Both pursued" (decided 13 Sep 2026). When
role-based permissions are built these become Admin-only, server-enforced.
Every action already records who, when and why.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .clock import now_utc
from .ids import next_reference_id
from .messages import not_found, refusal
from .models import (
    Account,
    Deal,
    DealRegistration,
    Lead,
    Opportunity,
    PursuitGroup,
    RegistrationConflict,
    Stage,
)
from .progression import PILOT_STATUS
from .revenue import COUNTED_STATUSES, revenue_context, revenue_of

#: Written only by this module. Routers skip them in their write loops, the
#: same way SYSTEM_STAMPED is skipped: a client never decides them.
PURSUIT_STAMPED = frozenset({"pursuit_group", "is_primary_pursuit"})

BOTH_PURSUED = "BOTH_PURSUED"

GROUP_ID_PATTERN = re.compile(r"^PG-(\d+)$")

MODEL_OF_PREFIX = {"LEAD": ("leads", Lead), "OPP": ("opportunities", Opportunity), "DEAL": ("deals", Deal)}


# =========================================================================
# CHAINS
# =========================================================================


def record_by_id(db: Session, record_id: str) -> tuple[str, Any]:
    prefix = (record_id or "").split("-", 1)[0]
    if prefix not in MODEL_OF_PREFIX:
        raise not_found("record", record_id=record_id)
    module, model = MODEL_OF_PREFIX[prefix]
    record = db.get(model, record_id)
    if record is None:
        raise not_found("record", record_id=record_id)
    return module, record


ID_COLUMN = {"leads": "lead_id", "opportunities": "opportunity_id", "deals": "deal_id"}


def id_of(module: str, record: Any) -> str:
    return getattr(record, ID_COLUMN[module])


def root_of(db: Session, module: str, record: Any) -> str:
    """The first record of the chain this record belongs to."""
    if module == "leads":
        return record.lead_id
    if module == "opportunities":
        return record.parent_lead or record.opportunity_id
    if record.parent_lead:
        return record.parent_lead
    if record.parent_opportunity:
        opp = db.get(Opportunity, record.parent_opportunity)
        if opp is not None:
            return opp.parent_lead or opp.opportunity_id
    return record.deal_id


def chain(db: Session, root: str) -> list[tuple[str, Any]]:
    """Every record of one pursuit, first to last."""
    out: list[tuple[str, Any]] = []
    if root.startswith("LEAD-"):
        lead = db.get(Lead, root)
        if lead is not None:
            out.append(("leads", lead))
        opps = list(db.scalars(select(Opportunity).where(Opportunity.parent_lead == root)))
    elif root.startswith("OPP-"):
        opp = db.get(Opportunity, root)
        opps = [opp] if opp is not None else []
    else:
        deal = db.get(Deal, root)
        return [("deals", deal)] if deal is not None else []

    out += [("opportunities", o) for o in opps]
    opp_ids = [o.opportunity_id for o in opps]
    conditions = [Deal.parent_opportunity.in_(opp_ids)] if opp_ids else []
    if root.startswith("LEAD-"):
        conditions.append(Deal.parent_lead == root)
    if conditions:
        out += [("deals", d) for d in db.scalars(select(Deal).where(or_(*conditions)))]
    return out


def tip(records: list[tuple[str, Any]]) -> tuple[str, Any] | None:
    """
    The live end of a chain. A Deal beats an Opportunity beats a Lead; within a
    module the record that is not CONVERTED wins. A paid-pilot Deal spun off a
    Lead (status POC_PILOT_DEAL) is its own revenue, not the pursuit's
    booking, and is passed over while any other Deal exists.
    """
    rank = {"leads": 0, "opportunities": 1, "deals": 2}

    def key(item):
        module, record = item
        converted = getattr(record, "lead_status", None) == "CONVERTED"
        pilot = module == "deals" and record.lead_status == PILOT_STATUS
        return (rank[module], not converted, not pilot)

    return max(records, key=key) if records else None


def is_open(record: Any) -> bool:
    return getattr(record, "lead_status", None) in COUNTED_STATUSES


def end_client_of(db: Session, module: str, record: Any) -> str | None:
    """Opportunities read End Client through their Lead; Deals carry their own."""
    if module == "opportunities":
        lead = db.get(Lead, record.parent_lead) if record.parent_lead else None
        return lead.end_client if lead else None
    if module == "deals" and not record.end_client:
        root = root_of(db, module, record)
        lead = db.get(Lead, root) if root.startswith("LEAD-") else None
        return lead.end_client if lead else None
    return record.end_client


def member_roots(db: Session, group_id: str) -> list[str]:
    roots: list[str] = []
    for module, model in (("leads", Lead), ("opportunities", Opportunity), ("deals", Deal)):
        for record in db.scalars(select(model).where(model.pursuit_group == group_id)):
            root = root_of(db, module, record)
            if root not in roots:
                roots.append(root)
    return sorted(roots)


def _set_chain(db: Session, root: str, group_id: str | None, primary: bool) -> list[str]:
    """Write membership onto every record of a chain. Returns what moved."""
    moved = []
    for module, record in chain(db, root):
        if record.pursuit_group != group_id or record.is_primary_pursuit != primary:
            moved.append(id_of(module, record))
        record.pursuit_group = group_id
        record.is_primary_pursuit = primary
    return moved


def restamp(db: Session, group: PursuitGroup) -> None:
    for root in member_roots(db, group.group_id):
        _set_chain(db, root, group.group_id, root == group.primary_pursuit)


def _next_group_id(db: Session) -> str:
    highest = 0
    for existing in db.scalars(select(PursuitGroup.group_id)):
        match = GROUP_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "pursuit_groups", "PG", 4, highest)


def _audit(db: Session, group_id: str, actor: str, event: str, reason: str | None, **changes) -> None:
    """
    One row on the group, and one on the live record of every pursuit it
    touched, so each record's History says what happened to it and why.

    The reason rides as a `__reason` entry in `changed`: audit_log has no reason
    column, and a transition-style table for one sentence would be a second
    audit trail. src/lib/timeline.ts lifts it out for the `pursuit` action.
    """
    entries = [{"field": "__event", "from": None, "to": event}]
    if reason:
        entries.append({"field": "__reason", "from": None, "to": reason})
    for field, (old, new) in changes.items():
        entries.append({"field": field, "from": old, "to": new})
    record_audit(
        db, module="pursuit_groups", record_id=group_id, action="pursuit", actor=actor, changed=entries
    )
    for root in {r for r in _roots_named(changes)}:
        live = tip(chain(db, root))
        if live is not None:
            module, record = live
            record_audit(
                db,
                module=module,
                record_id=id_of(module, record),
                action="pursuit",
                actor=actor,
                changed=entries,
            )


def _live_name(db: Session, root: str) -> str | None:
    """A pursuit as a person calls it — its live record's name, never its id."""
    records = chain(db, root)
    live = tip(records)
    if live is None:
        return None
    record, first = live[1], records[0][1]
    return (
        getattr(record, "opportunity_name", None)
        or getattr(record, "deal_name", None)
        or getattr(first, "opportunity_name", None)
    )


def group_display_name(db: Session, group: PursuitGroup | None) -> str | None:
    """
    "Al Waha Integrated Command & Control Centre at Madinat Al Waha Development
    Authority". A group is the same project pursued through more than one
    partner, so it is named after the project and the client — the primary
    pursuit's name first, then any member's, then the primary registration's
    project for a group whose leads do not exist yet.
    """
    if group is None:
        return None
    roots = member_roots(db, group.group_id)
    ordered = ([group.primary_pursuit] if group.primary_pursuit in roots else []) + [
        r for r in roots if r != group.primary_pursuit
    ]
    project = next((name for name in (_live_name(db, r) for r in ordered) if name), None)
    if not project and group.primary_registration:
        registration = db.get(DealRegistration, group.primary_registration)
        project = registration.project_name if registration is not None else None
    client = db.get(Account, group.end_client) if group.end_client else None
    project = project or "Pursuit group"
    return f"{project} at {client.account_name}" if client is not None else project


def group_names(db: Session) -> dict[str, str]:
    """group id -> display name, for the list endpoints' label joins."""
    return {g.group_id: group_display_name(db, g) or g.group_id for g in db.scalars(select(PursuitGroup))}


def _registration_label(db: Session, registration_id: str | None) -> str:
    registration = db.get(DealRegistration, registration_id) if registration_id else None
    if registration is None:
        return "a deal registration"
    partner = db.get(Account, registration.partner) if registration.partner else None
    who = partner.account_name if partner is not None else "a partner"
    return f"{who}'s registration"


def _roots_named(changes: dict[str, tuple[Any, Any]]) -> Iterable[str]:
    for old, new in changes.values():
        for value in (old, new):
            if isinstance(value, str) and value.split("-", 1)[0] in ("LEAD", "OPP", "DEAL"):
                yield value
            if isinstance(value, list):
                yield from (v for v in value if isinstance(v, str))


# =========================================================================
# GROUP ACTIONS
# =========================================================================


def _resolve_member(db: Session, record_id: str) -> tuple[str, str, Any]:
    """record id -> (root, live module, live record), refusing a non-pursuit."""
    module, record = record_by_id(db, record_id)
    root = root_of(db, module, record)
    live = tip(chain(db, root))
    if live is None:
        raise not_found("pursuit", record_id=record_id)
    return root, live[0], live[1]


def create_group(
    db: Session,
    *,
    members: list[str],
    primary: str,
    actor: str,
    reason: str | None,
    source_conflict: str | None = None,
    primary_registration: str | None = None,
    end_client: str | None = None,
) -> PursuitGroup:
    resolved = {}
    for record_id in members:
        root, module, record = _resolve_member(db, record_id)
        resolved[root] = (module, record)
    primary_root = _resolve_member(db, primary)[0] if primary else None
    if primary_root is not None and primary_root not in resolved:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("PRIMARY_NOT_A_MEMBER", "The primary pursuit must be one of the pursuits in the group."),
        )

    clients = {end_client_of(db, m, r) for m, r in resolved.values()}
    if end_client is not None:
        clients.add(end_client)
    if None in clients or len(clients) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("END_CLIENT_MISMATCH", "All pursuits in a group must have the same End Client."),
        )

    for root, (module, record) in resolved.items():
        if record.pursuit_group:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                refusal(
                    "ALREADY_GROUPED",
                    f"{_live_name(db, root) or 'This pursuit'} is already in "
                    f"{group_display_name(db, db.get(PursuitGroup, record.pursuit_group)) or 'another pursuit group'}.",
                    ["Add the other pursuits to that group instead."],
                    group_id=record.pursuit_group,
                ),
            )

    stamp = now_utc()
    group = PursuitGroup(
        group_id=_next_group_id(db),
        end_client=clients.pop(),
        primary_pursuit=primary_root,
        primary_registration=primary_registration,
        source_conflict=source_conflict,
        created_by=actor,
        created_date=stamp,
        modified_by=actor,
        modified_date=stamp,
    )
    db.add(group)
    db.flush()
    for root in resolved:
        _set_chain(db, root, group.group_id, root == primary_root)
    _audit(
        db,
        group.group_id,
        actor,
        "created",
        reason,
        members=(None, sorted(resolved)),
        primary_pursuit=(None, primary_root),
    )
    return group


def add_member(db: Session, group: PursuitGroup, record_id: str, *, actor: str, reason: str | None) -> str:
    root, module, record = _resolve_member(db, record_id)
    if record.pursuit_group == group.group_id:
        return root
    if record.pursuit_group:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "ALREADY_GROUPED",
                f"{_live_name(db, root) or 'This pursuit'} is already in "
                f"{group_display_name(db, db.get(PursuitGroup, record.pursuit_group)) or 'another pursuit group'}.",
            ),
        )
    if end_client_of(db, module, record) != group.end_client:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "END_CLIENT_MISMATCH",
                "This pursuit has a different End Client, so it can't join the group.",
            ),
        )
    _set_chain(db, root, group.group_id, root == group.primary_pursuit)
    _touch(group, actor)
    _audit(db, group.group_id, actor, "member_added", reason, member=(None, root))
    return root


def change_primary(db: Session, group: PursuitGroup, record_id: str, *, actor: str, reason: str) -> None:
    root = _resolve_member(db, record_id)[0]
    roots = member_roots(db, group.group_id)
    if root not in roots:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "NOT_A_MEMBER",
                f"{_live_name(db, root) or 'This pursuit'} is no longer in {group_display_name(db, group) or 'this group'}.",
                ["Reload the page to see the group as it is now."],
            ),
        )
    if root == group.primary_pursuit:
        return
    old = group.primary_pursuit
    group.primary_pursuit = root
    restamp(db, group)
    _touch(group, actor)
    _audit(db, group.group_id, actor, "primary_changed", reason, primary_pursuit=(old, root))


def remove_member(
    db: Session, group: PursuitGroup, record_id: str, *, actor: str, reason: str, new_primary: str | None
) -> None:
    root = _resolve_member(db, record_id)[0]
    roots = member_roots(db, group.group_id)
    if root not in roots:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "NOT_A_MEMBER",
                f"{_live_name(db, root) or 'This pursuit'} is no longer in {group_display_name(db, group) or 'this group'}.",
                ["Reload the page to see the group as it is now."],
            ),
        )
    remaining = [r for r in roots if r != root]

    if root == group.primary_pursuit and len(remaining) > 1:
        if not new_primary:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                refusal(
                    "NEW_PRIMARY_REQUIRED",
                    "This pursuit counts in the pipeline now.",
                    ["Choose which pursuit should count instead."],
                    options=remaining,
                ),
            )
        chosen = _resolve_member(db, new_primary)[0]
        if chosen not in remaining:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                refusal("NOT_A_MEMBER", "The new primary must be one of the pursuits left in the group."),
            )
        group.primary_pursuit = chosen

    _set_chain(db, root, None, True)
    # Leaving a group is the same statement as declining to join one: this is
    # not a duplicate of that pursuit. Recorded where the duplicate check reads
    # it, so the next End Client edit does not ask the question again.
    if root.startswith("LEAD-"):
        lead = db.get(Lead, root)
        if lead is not None and not lead.not_duplicate_reason:
            lead.not_duplicate_reason = reason

    _touch(group, actor)
    _audit(db, group.group_id, actor, "member_removed", reason, member=(root, None))

    if len(remaining) == 1 and group.primary_pursuit == root:
        group.primary_pursuit = remaining[0]
    restamp(db, group)
    dissolve_if_single(db, group, actor=actor)


def dissolve_if_single(db: Session, group: PursuitGroup, *, actor: str) -> bool:
    roots = member_roots(db, group.group_id)
    if len(roots) > 1:
        return False
    for root in roots:
        _set_chain(db, root, None, True)
    _audit(db, group.group_id, actor, "dissolved", "One pursuit left — nothing to de-duplicate.", members=(roots, None))
    db.delete(group)
    return True


def _touch(group: PursuitGroup, actor: str) -> None:
    group.modified_by = actor
    group.modified_date = now_utc()


# =========================================================================
# RULES THE ROUTERS CALL
# =========================================================================


def open_pursuits_for(db: Session, end_client: str | None, *, excluding_root: str | None) -> list[dict]:
    """Every open pursuit naming this End Client, one entry per chain."""
    if not end_client:
        return []
    roots: set[str] = set()
    for lead in db.scalars(select(Lead).where(Lead.end_client == end_client)):
        roots.add(lead.lead_id)
    for deal in db.scalars(select(Deal).where(Deal.end_client == end_client)):
        roots.add(root_of(db, "deals", deal))
    roots.discard(excluding_root or "")

    accounts = {a.account_id: a.account_name for a in db.scalars(select(Account))}
    out = []
    for root in sorted(roots):
        records = chain(db, root)
        live = tip(records)
        if live is None or not is_open(live[1]):
            continue
        module, record = live
        first = records[0][1]
        group = db.get(PursuitGroup, record.pursuit_group) if record.pursuit_group else None
        out.append(
            {
                "pursuit": root,
                "module": module,
                "record_id": id_of(module, record),
                "group_id": record.pursuit_group,
                "is_primary": record.is_primary_pursuit,
                # Names for the duplicate dialog — a person picks a pursuit by
                # what it is called, not by LEAD-00017.
                "name": _live_name(db, root),
                "partner_name": accounts.get(getattr(first, "customer_partner_si", None) or ""),
                "stage_number": stage_number(getattr(record, STAGE_FIELD[module], None)),
                "group_name": group_display_name(db, group) if group is not None else None,
            }
        )
    return out


def auto_join_from_conflict(db: Session, lead: Lead, *, actor: str) -> bool:
    """
    A lead registered under either side of a "Both pursued" conflict joins the
    group that decision created — primary if its registration is the one the
    decision named. Returns True when it joined.
    """
    if lead.pursuit_group or not lead.partner_deal_registration:
        return False
    group = _group_for_registration(db, lead.partner_deal_registration)
    if group is None:
        return False
    if lead.end_client != group.end_client:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "END_CLIENT_MISMATCH",
                f"{_registration_label(db, lead.partner_deal_registration)} belongs to "
                f"{group_display_name(db, group) or 'a pursuit group'} for a different End Client.",
                ["Set this lead's End Client to match, or link a different registration."],
            ),
        )
    root = lead.lead_id
    becomes_primary = (
        group.primary_pursuit is None and lead.partner_deal_registration == group.primary_registration
    )
    if becomes_primary:
        group.primary_pursuit = root
    _set_chain(db, root, group.group_id, root == group.primary_pursuit)
    _touch(group, actor)
    _audit(
        db,
        group.group_id,
        actor,
        "member_added",
        f"Created from {_registration_label(db, lead.partner_deal_registration)}, one side of a conflict decided "
        "as both pursued.",
        member=(None, root),
        **({"primary_pursuit": (None, root)} if becomes_primary else {}),
    )
    return True


def _group_for_registration(db: Session, registration_id: str) -> PursuitGroup | None:
    conflict = db.scalars(
        select(RegistrationConflict)
        .where(RegistrationConflict.decision == BOTH_PURSUED)
        .where(
            or_(
                RegistrationConflict.registration_a == registration_id,
                RegistrationConflict.registration_b == registration_id,
            )
        )
    ).first()
    if conflict is None:
        return None
    return db.scalars(select(PursuitGroup).where(PursuitGroup.source_conflict == conflict.conflict_id)).first()


def guard_possible_duplicate(
    db: Session, lead: Lead, *, actor: str, join_pursuit_of: str | None, checking: bool
) -> None:
    """
    Runs after a lead's values are applied and before commit. `checking` is
    True on create, and on update when End Client was sent.

    A lead joins a group when asked to (join_pursuit_of), or on its own when its
    registration belongs to a "Both pursued" conflict. Otherwise, if another
    open pursuit names the same End Client, the save is refused with the
    matches — unless not_duplicate_reason says why this is a different project.
    """
    if join_pursuit_of:
        root, module, other = _resolve_member(db, join_pursuit_of)
        if root == lead.lead_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                refusal("CANNOT_JOIN_ITSELF", "A lead can't join its own pursuit group."),
            )
        other_name = _live_name(db, root) or "an existing pursuit"
        if other.pursuit_group:
            add_member(
                db,
                db.get(PursuitGroup, other.pursuit_group),
                lead.lead_id,
                actor=actor,
                reason=f"Joined as the same project as {other_name}.",
            )
        else:
            create_group(
                db,
                members=[root, lead.lead_id],
                primary=root,
                actor=actor,
                reason=(
                    f"{lead.opportunity_name or 'This lead'} saved as the same project as {other_name}, "
                    "which was there first."
                ),
            )
        return

    if auto_join_from_conflict(db, lead, actor=actor):
        return

    if not checking or lead.pursuit_group or (lead.not_duplicate_reason or "").strip():
        return
    # An expansion lead opened off a Deal shares that Deal's End Client by
    # construction and is a new project by definition (Stage 9 — Expansion).
    if lead.parent_deal:
        return

    # A lead made from a registration Partners already declared "a different
    # project" is not asked again about the pursuits that answer was about. It
    # IS still asked about every other open pursuit at the End Client — a direct
    # lead, another partner's lead Partners never compared it with — because
    # the Partners answer was given about a registration, not about those. The
    # dialog is offered that answer to pre-fill, so confirming it is one click.
    registration = (
        db.get(DealRegistration, lead.partner_deal_registration) if lead.partner_deal_registration else None
    )
    partners_reason = ((registration.not_conflict_reason if registration else None) or "").strip()

    matches = open_pursuits_for(db, lead.end_client, excluding_root=lead.lead_id)
    ruled = _pursuits_ruled_different(db, registration)
    matches = [m for m in matches if m["pursuit"] not in ruled]
    if matches:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "POSSIBLE_DUPLICATE",
                "This End Client already has an open pursuit.",
                [
                    "Same project: join its group. Only one pursuit counts in the pipeline total.",
                    "Different project: tell us why, and it's saved on its own.",
                ],
                matches=matches,
                suggested_reason=partners_reason or None,
            ),
        )

    # Nothing left to ask. Partners' answer is the lead's reason, so the Leads
    # form shows Not a Duplicate Reason with what Partners recorded.
    if partners_reason:
        lead.not_duplicate_reason = partners_reason


def _pursuits_ruled_different(db: Session, registration: DealRegistration | None) -> set[str]:
    """
    The pursuits Partners already ruled a different project from this
    registration: the leads of every registration the two were declared
    "different project" against. Read in both directions — _dismiss in
    registration_matching.py writes both sides, but either list can be edited.

    Only these are waived by the Partners answer. Nothing else is.
    """
    if registration is None:
        return set()
    others = set(registration.not_conflict_with or [])
    if registration.end_client:
        for other in db.scalars(
            select(DealRegistration).where(DealRegistration.end_client == registration.end_client)
        ):
            if registration.registration_id in (other.not_conflict_with or []):
                others.add(other.registration_id)
    if not others:
        return set()
    linked = [
        r.linked_lead
        for r in db.scalars(select(DealRegistration).where(DealRegistration.registration_id.in_(others)))
        if r.linked_lead
    ]
    leads = db.scalars(
        select(Lead).where(or_(Lead.partner_deal_registration.in_(others), Lead.lead_id.in_(linked)))
    )
    return {root_of(db, "leads", lead) for lead in leads}


def inherit_on_create(db: Session, module: str, record: Any) -> None:
    """An Opportunity or Deal takes its parent's group, whatever the body said."""
    parent = None
    if module == "opportunities" and record.parent_lead:
        parent = db.get(Lead, record.parent_lead)
    elif module == "deals":
        if record.parent_opportunity:
            parent = db.get(Opportunity, record.parent_opportunity)
        elif record.parent_lead:
            parent = db.get(Lead, record.parent_lead)
    record.pursuit_group = parent.pursuit_group if parent is not None else None
    record.is_primary_pursuit = parent.is_primary_pursuit if parent is not None else True


def guard_win(db: Session, deal: Deal) -> None:
    """Called after inherit_on_create. Actual revenue never comes from a record
    that does not count."""
    if deal.pursuit_group and not deal.is_primary_pursuit and deal.lead_status != PILOT_STATUS:
        group = db.get(PursuitGroup, deal.pursuit_group)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "SECONDARY_CANNOT_WIN",
                "Only the pursuit that counts in its group can be won.",
                ["Make this pursuit the primary first."],
                group_id=deal.pursuit_group,
                group_name=group_display_name(db, group),
                primary_pursuit=group.primary_pursuit if group else None,
                primary_name=_live_name(db, group.primary_pursuit) if group and group.primary_pursuit else None,
            ),
        )


def guard_close(db: Session, module: str, record: Any, new_status: str | None) -> None:
    """Called before a status change is applied."""
    if new_status != "CLOSED_LOST" or getattr(record, "lead_status", None) == "CLOSED_LOST":
        return
    if not record.pursuit_group or not record.is_primary_pursuit:
        return
    root = root_of(db, module, record)
    others = [
        o
        for o in open_pursuits_in(db, record.pursuit_group)
        if o["pursuit"] != root
    ]
    if others:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "PRIMARY_HAS_OPEN_SECONDARIES",
                "You're closing the pursuit that counts.",
                [
                    "Another pursuit of this project is still open.",
                    "Choose which one counts next. Your close is saved right after.",
                ],
                group_id=record.pursuit_group,
                open=others,
            ),
        )


def open_pursuits_in(db: Session, group_id: str) -> list[dict]:
    out = []
    for root in member_roots(db, group_id):
        live = tip(chain(db, root))
        if live is not None and is_open(live[1]):
            out.append({"pursuit": root, "module": live[0], "record_id": id_of(*live)})
    return out


def guard_end_client_change(db: Session, record: Any, sent: set[str], new_value: str | None) -> None:
    if "end_client" in sent and record.pursuit_group and new_value != record.end_client:
        name = group_display_name(db, db.get(PursuitGroup, record.pursuit_group))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "REMOVE_FROM_GROUP_FIRST",
                f"This pursuit is in {name or 'a pursuit group'}, so its End Client can't change.",
                ["Remove it from the group first, then change the End Client."],
                group_id=record.pursuit_group,
            ),
        )


# =========================================================================
# CONFLICT DECISIONS
# =========================================================================


def apply_conflict_decision(db: Session, conflict: RegistrationConflict, *, previous: str | None, actor: str) -> None:
    """
    "Both pursued" names a primary registration and creates the group. Leads
    already registered under either side join it now; later ones join as they
    are saved (auto_join_from_conflict).

    Moving a conflict AWAY from "Both pursued" while its group still holds
    pursuits is refused: dissolving it would put the secondary's value straight
    back into the pipeline, which is a revenue decision a decision field should
    not make as a side effect.
    """
    group = db.scalars(select(PursuitGroup).where(PursuitGroup.source_conflict == conflict.conflict_id)).first()

    if conflict.decision != BOTH_PURSUED:
        if previous == BOTH_PURSUED and group is not None and len(member_roots(db, group.group_id)) > 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                refusal(
                    "GROUP_STILL_HAS_PURSUITS",
                    f"{group_display_name(db, group) or 'The pursuit group'} still holds this conflict's pursuits.",
                    ["Remove them from the group first, then change the decision."],
                    group_id=group.group_id,
                ),
            )
        if group is not None:
            dissolve_if_single(db, group, actor=actor)
        return

    pair = {conflict.registration_a, conflict.registration_b} - {None}
    if conflict.primary_registration not in pair:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "PRIMARY_REGISTRATION_REQUIRED",
                "You chose to pursue both registrations.",
                ["Pick which one counts in the pipeline: Registration A or B."],
            ),
        )

    registrations = [db.get(DealRegistration, r) for r in sorted(pair)]
    end_client = next((r.end_client for r in registrations if r is not None and r.end_client), None)

    if group is None:
        stamp = now_utc()
        group = PursuitGroup(
            group_id=_next_group_id(db),
            end_client=end_client,
            primary_registration=conflict.primary_registration,
            source_conflict=conflict.conflict_id,
            created_by=actor,
            created_date=stamp,
            modified_by=actor,
            modified_date=stamp,
        )
        db.add(group)
        db.flush()
        _audit(
            db,
            group.group_id,
            actor,
            "created",
            f"Conflict {conflict.conflict_id} decided: both pursued.",
            primary_registration=(None, conflict.primary_registration),
        )
    elif group.primary_registration != conflict.primary_registration:
        old = group.primary_registration
        group.primary_registration = conflict.primary_registration
        _touch(group, actor)
        _audit(
            db,
            group.group_id,
            actor,
            "primary_registration_changed",
            f"Conflict {conflict.conflict_id} changed its primary registration.",
            primary_registration=(old, conflict.primary_registration),
        )

    for registration in registrations:
        if registration is None:
            continue
        leads = list(
            db.scalars(
                select(Lead).where(
                    or_(
                        Lead.partner_deal_registration == registration.registration_id,
                        Lead.lead_id == (registration.linked_lead or ""),
                    )
                )
            )
        )
        for lead in leads:
            if lead.pursuit_group == group.group_id:
                continue
            if lead.pursuit_group:
                continue  # already grouped elsewhere; a person decides, not this loop
            if lead.lead_id == registration.linked_lead and not lead.partner_deal_registration:
                lead.partner_deal_registration = registration.registration_id
            auto_join_from_conflict(db, lead, actor=actor)

    # The primary registration's lead may already be a member as a secondary
    # (joined before the decision named it). The decision is the answer.
    if group.primary_pursuit is None:
        for root in member_roots(db, group.group_id):
            lead = db.get(Lead, root) if root.startswith("LEAD-") else None
            if lead is not None and lead.partner_deal_registration == conflict.primary_registration:
                group.primary_pursuit = root
                restamp(db, group)
                break


# =========================================================================
# READING A GROUP
# =========================================================================


STAGE_FIELD = {"leads": "project_stage", "opportunities": "project_stage", "deals": "deal_stage"}


def stage_number(value: str | None) -> int | None:
    match = re.match(r"^(\d+)", value or "")
    return int(match.group(1)) if match else None


def stage_names(db: Session) -> dict[int, str]:
    """stage number -> "Stage 3 — Prescription", from the stages table — never typed here."""
    return {s.stage: f"Stage {s.stage} — {s.name}" for s in db.scalars(select(Stage))}


def serialise_group(db: Session, group: PursuitGroup) -> dict:
    ctx = revenue_context(db)
    accounts = {a.account_id: a.account_name for a in db.scalars(select(Account))}
    stages = stage_names(db)
    members = []
    for root in member_roots(db, group.group_id):
        records = chain(db, root)
        live = tip(records)
        if live is None:
            continue
        module, record = live
        name = record.opportunity_name if module == "leads" else (
            record.deal_name if module == "deals" else None
        )
        if name is None and root.startswith("LEAD-"):
            first = db.get(Lead, root)
            name = first.opportunity_name if first else None
        partner = record.customer_partner_si if module != "opportunities" else None
        if partner is None and root.startswith("LEAD-"):
            first = db.get(Lead, root)
            partner = first.customer_partner_si if first else None
        stage = getattr(record, STAGE_FIELD[module], None)
        members.append(
            {
                "pursuit": root,
                "is_primary": root == group.primary_pursuit,
                "is_open": is_open(record),
                "module": module,
                "record_id": id_of(module, record),
                "name": name,
                "partner": partner,
                "partner_name": accounts.get(partner or ""),
                "stage": stage,
                "stage_number": stage_number(stage),
                "stage_name": stages.get(stage_number(stage)),
                "status": getattr(record, "lead_status", None),
                "chain": [{"module": m, "record_id": id_of(m, r)} for m, r in records],
                "revenue": revenue_of(ctx, module, record),
            }
        )

    return {
        "id": group.group_id,
        "group_id": group.group_id,
        "name": group_display_name(db, group),
        "end_client": group.end_client,
        "end_client_name": accounts.get(group.end_client or ""),
        "primary_pursuit": group.primary_pursuit,
        "primary_registration": group.primary_registration,
        "source_conflict": group.source_conflict,
        "created_by": group.created_by,
        "created_date": group.created_date,
        "modified_by": group.modified_by,
        "modified_date": group.modified_date,
        "members": members,
        "alerts": alerts_for(group, members),
    }


def alerts_for(group: PursuitGroup, members: list[dict]) -> list[dict]:
    """
    On-screen notices, computed when the group is read. Nothing here is sent
    to anyone and nothing waits for a timer (CLAUDE.md hard rule 6); a screen
    that wants the notice asks for the group.
    """
    alerts = []
    primary = next((m for m in members if m["is_primary"]), None)
    if primary is None:
        alerts.append(
            {
                "code": "NO_PRIMARY",
                "level": "warning",
                "message": "Nothing in this group counts in the pipeline yet.",
                "details": ["The lead for the chosen registration hasn't been created."],
            }
        )
        return alerts

    for member in members:
        if member["is_primary"] or not member["is_open"]:
            continue
        ahead = (member["stage_number"] or -1) > (primary["stage_number"] or -1)
        if ahead and primary["is_open"]:
            alerts.append(
                {
                    "code": "SECONDARY_AHEAD",
                    "level": "warning",
                    "pursuit": member["pursuit"],
                    "message": f"{member['name'] or 'Another pursuit'} is further along than the pursuit that counts.",
                    "details": [
                        f"{member['name'] or 'That pursuit'}: {member.get('stage_name') or member['stage_number']}",
                        f"Counting now: {primary.get('stage_name') or primary['stage_number']}",
                    ],
                }
            )
    if not primary["is_open"] and any(m["is_open"] for m in members if not m["is_primary"]):
        alerts.append(
            {
                "code": "PRIMARY_CLOSED",
                "level": "warning",
                "message": "The pursuit that counted is closed, but another is still open.",
                "details": ["Choose which one counts now."],
            }
        )
    if primary["module"] == "deals" and primary["is_open"]:
        open_secondaries = [m["record_id"] for m in members if not m["is_primary"] and m["is_open"]]
        if open_secondaries:
            alerts.append(
                {
                    "code": "WON_WITH_OPEN_SECONDARIES",
                    "level": "info",
                    "open": open_secondaries,
                    "message": (
                        f"This project is won. {len(open_secondaries)} other "
                        f"{'pursuit' if len(open_secondaries) == 1 else 'pursuits'} of it "
                        f"{'is' if len(open_secondaries) == 1 else 'are'} still open."
                    ),
                    "details": ['Close them as lost, with the reason "Partner conflict".'],
                }
            )
    return alerts

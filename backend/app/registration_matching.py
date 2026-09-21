"""
Deal registration conflicts — which registrations collide, and raising the record.

EVERY RULE IS HERE. routers/registrations.py calls in on save; routers/conflicts.py
calls in for Who Registered First. Nothing in the browser decides a collision any
more: until Sep 2026 lib/partners.ts::collidingRegistrations matched two
registrations client-side, only when somebody opened a Conflict tab, only on an
exact project name, and created nothing. A conflict nobody happened to look at
did not exist.

    possible_matches            the live registrations this one may collide with
    resolve_possible_conflicts  the save's answer: raise a conflict with each
                                named match, record "different project" (with a
                                reason) for the rest — or refuse the save (422
                                POSSIBLE_CONFLICT) and hand back the matches
    raise_conflict              create the conflict record, Open, pair stamped
    who_registered_first        derived from the two Submitted Dates, never typed

WHAT COUNTS AS A MATCH
----------------------
Same End Client, both registrations LIVE (Submitted, Acknowledged, Active,
Extended — and an exclusivity window that has not closed), and a Project Name
that is the same or SIMILAR. Similar is deliberately loose: a person confirms
every match, so a false positive costs one click and a false negative costs an
unadjudicated conflict. "Al Waha ICCC" is caught against "Al Waha Integrated
Command & Control Centre" — see similarity().

A pair already in a conflict record, or already declared "a different project",
is never asked about again.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .clock import now_utc, today_company
from .ids import next_reference_id
from .models import Account, DealRegistration, Lead, RegistrationConflict

WITHDRAWN = "WITHDRAWN"

#: A registration in one of these can still collide, be withdrawn, or have a
#: lead created under it. Blank is Submitted by another name — see
#: lib/partners.ts, which reads a blank status as awaiting acknowledgement.
LIVE_STATUSES = frozenset({None, "", "SUBMITTED", "ACKNOWLEDGED", "ACTIVE", "EXTENDED"})

#: Five characters, the same floor as a pursuit group reason: enough to keep
#: out "x" and "ok" without pretending to judge the sentence.
MIN_REASON = 5

CONFLICT_ID_PATTERN = re.compile(r"^CONF-(\d+)$")

REGISTRATION_A = "REGISTRATION_A"
REGISTRATION_B = "REGISTRATION_B"
SAME_DAY = "SAME_DAY"

#: Two names this similar are put in front of a person. See similarity().
SIMILAR_AT = 0.6

#: Words that say nothing about WHICH project it is.
_STOP_WORDS = frozenset(
    {"a", "an", "and", "at", "by", "for", "in", "of", "on", "the", "to", "with", "project", "programme", "program"}
)


# =========================================================================
# NAMES
# =========================================================================


def account_names(db: Session) -> dict[str, str]:
    return {a.account_id: a.account_name for a in db.scalars(select(Account))}


def registration_name(reg: DealRegistration, accounts: dict[str, str]) -> str:
    """"Gulfstar Systems Integration LLC · Al Waha Integrated Command & Control
    Centre" — what a person calls a registration. Never its REG- id."""
    partner = accounts.get(reg.partner or "") or "No partner"
    return f"{partner} · {reg.project_name or 'Untitled project'}"


def conflict_name(conflict: RegistrationConflict, partner_of: dict[str, str]) -> str:
    a = partner_of.get(conflict.registration_a or "") or "a registration"
    b = partner_of.get(conflict.registration_b or "") or "a registration"
    return f"Conflict: {a} vs {b}"


def partner_names_of_registrations(db: Session, accounts: dict[str, str]) -> dict[str, str]:
    return {
        r.registration_id: accounts.get(r.partner or "") or "No partner"
        for r in db.scalars(select(DealRegistration))
    }


# =========================================================================
# STATE
# =========================================================================


def is_live_status(value: str | None) -> bool:
    return value in LIVE_STATUSES


def is_live(reg: DealRegistration, today: date | None = None) -> bool:
    """Status says live AND the exclusivity window, if one was granted, is open.

    Both, because the stored status and the dates can disagree — nothing in the
    register expires a registration (see lib/partners.ts::registrationState).
    """
    if not is_live_status(reg.registration_status):
        return False
    expiry = reg.exclusivity_expiry_date
    return not (expiry and expiry < (today or today_company()))


# =========================================================================
# SIMILARITY
# =========================================================================


def _slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _tokens(value: str | None) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (value or "").lower()) if w not in _STOP_WORDS]


def _acronym_run(acronym: str, words: list[str]) -> set[int]:
    """Indices of a contiguous run of `words` whose initials spell `acronym`."""
    n = len(acronym)
    for start in range(len(words) - n + 1):
        if "".join(w[0] for w in words[start : start + n]) == acronym:
            return set(range(start, start + n))
    return set()


def similarity(a: str | None, b: str | None) -> float:
    """
    Share of the words in both names that the other name accounts for — the
    same word, or an acronym standing for a run of words ("iccc" for
    "integrated command control centre"). 1.0 is the same name.

    Not edit distance: project names differ by whole words ("Phase 2", "O&M"),
    not by typos, and a place name shared by two unrelated projects ("Al Waha
    Water Network" vs "Al Waha ICCC") must stay under the threshold.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0

    def covered(own: list[str], other: list[str]) -> int:
        other_set, own_set = set(other), set(own)
        hit = {i for i, t in enumerate(own) if t in other_set}
        for i, t in enumerate(own):
            if i not in hit and len(t) >= 3 and _acronym_run(t, other):
                hit.add(i)
        for t in other:
            if len(t) >= 3 and t not in own_set:
                hit |= _acronym_run(t, own)
        return len(hit)

    return (covered(ta, tb) + covered(tb, ta)) / (len(ta) + len(tb))


def same_project(a: str | None, b: str | None) -> bool:
    return bool(_slug(a)) and (_slug(a) == _slug(b) or similarity(a, b) >= SIMILAR_AT)


# =========================================================================
# CONFLICT RECORDS
# =========================================================================


def conflicts_of(db: Session, registration_id: str) -> list[RegistrationConflict]:
    return list(
        db.scalars(
            select(RegistrationConflict).where(
                or_(
                    RegistrationConflict.registration_a == registration_id,
                    RegistrationConflict.registration_b == registration_id,
                )
            )
        )
    )


def pair_conflict(db: Session, a: str | None, b: str | None) -> RegistrationConflict | None:
    if not a or not b:
        return None
    return db.scalars(
        select(RegistrationConflict).where(
            or_(
                (RegistrationConflict.registration_a == a) & (RegistrationConflict.registration_b == b),
                (RegistrationConflict.registration_a == b) & (RegistrationConflict.registration_b == a),
            )
        )
    ).first()


def who_registered_first(a: DealRegistration | None, b: DealRegistration | None) -> str | None:
    """Registration A / Registration B / Same day, off the Submitted Dates.

    Blank when either date is missing: "first" cannot be judged, and a guessed
    answer to adjudication criterion one is worse than an empty one.
    """
    if a is None or b is None or a.submitted_date is None or b.submitted_date is None:
        return None
    if a.submitted_date < b.submitted_date:
        return REGISTRATION_A
    if b.submitted_date < a.submitted_date:
        return REGISTRATION_B
    return SAME_DAY


def who_registered_first_for(db: Session, conflict: RegistrationConflict) -> str | None:
    a = db.get(DealRegistration, conflict.registration_a) if conflict.registration_a else None
    b = db.get(DealRegistration, conflict.registration_b) if conflict.registration_b else None
    return who_registered_first(a, b)


def _next_conflict_id(db: Session) -> str:
    highest = 0
    for existing in db.scalars(select(RegistrationConflict.conflict_id)):
        match = CONFLICT_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "conflicts", "CONF", 4, highest)


def raise_conflict(
    db: Session, existing: DealRegistration, incoming: DealRegistration, *, actor: str
) -> RegistrationConflict:
    """
    An OPEN conflict record for one pair — no decision yet. Registration A is
    whichever was submitted first (the existing one on a tie), so the slot
    order means something a person can check against the dates.
    """
    earlier_first = (existing.submitted_date or date.max) <= (incoming.submitted_date or date.max)
    a, b = (existing, incoming) if earlier_first else (incoming, existing)

    stamp = now_utc()
    conflict = RegistrationConflict(
        conflict_id=_next_conflict_id(db),
        registration_a=a.registration_id,
        registration_b=b.registration_id,
        both_partners_notified=False,
        created_by=actor,
        created_date=stamp,
        modified_by=actor,
        modified_date=stamp,
    )
    conflict.who_registered_first = who_registered_first(a, b)
    db.add(conflict)
    db.flush()
    record_audit(
        db,
        module="conflicts",
        record_id=conflict.conflict_id,
        action="created",
        actor=actor,
        changed_fields=["registration_a", "registration_b", "who_registered_first"],
    )
    return conflict


# =========================================================================
# MATCHING AND THE SAVE'S ANSWER
# =========================================================================


def possible_matches(db: Session, reg: DealRegistration) -> list[DealRegistration]:
    """Live registrations this one may collide with, oldest submission first."""
    if not reg.end_client or not _slug(reg.project_name) or not is_live(reg):
        return []
    dismissed = set(reg.not_conflict_with or [])
    today = today_company()
    out = []
    for other in db.scalars(
        select(DealRegistration)
        .where(DealRegistration.end_client == reg.end_client)
        .where(DealRegistration.registration_id != reg.registration_id)
    ):
        if other.registration_id in dismissed or reg.registration_id in set(other.not_conflict_with or []):
            continue
        if not is_live(other, today) or not same_project(reg.project_name, other.project_name):
            continue
        if pair_conflict(db, reg.registration_id, other.registration_id) is not None:
            continue
        out.append(other)
    return sorted(out, key=lambda r: (r.submitted_date or date.max, r.registration_id))


def match_row(other: DealRegistration, reg: DealRegistration, accounts: dict[str, str]) -> dict[str, Any]:
    """One match, described for the dialog — names, never a REG- id to read."""
    return {
        "registration_id": other.registration_id,
        "name": registration_name(other, accounts),
        "partner": other.partner,
        "partner_name": accounts.get(other.partner or ""),
        "project_name": other.project_name,
        "end_client_name": accounts.get(other.end_client or ""),
        "submitted_date": other.submitted_date.isoformat() if other.submitted_date else None,
        "registration_status": other.registration_status,
        "exclusivity_expiry_date": (
            other.exclusivity_expiry_date.isoformat() if other.exclusivity_expiry_date else None
        ),
        "same_partner": bool(other.partner) and other.partner == reg.partner,
    }


def _dismiss(db: Session, reg: DealRegistration, other: DealRegistration, reason: str, actor: str) -> None:
    """Both sides remember "a different project", so neither asks again."""
    if other.registration_id not in (reg.not_conflict_with or []):
        # Rebound, not appended: SQLAlchemy does not see a JSONB list mutated in place.
        reg.not_conflict_with = [*(reg.not_conflict_with or []), other.registration_id]
    reg.not_conflict_reason = reason
    if reg.registration_id not in (other.not_conflict_with or []):
        before = list(other.not_conflict_with or [])
        other.not_conflict_with = [*before, reg.registration_id]
        if not (other.not_conflict_reason or "").strip():
            other.not_conflict_reason = reason
        record_audit(
            db,
            module="registrations",
            record_id=other.registration_id,
            action="updated",
            actor=actor,
            changed_fields=["not_conflict_with"],
            changed=[{"field": "not_conflict_with", "from": before, "to": other.not_conflict_with}],
        )


def resolve_possible_conflicts(
    db: Session,
    reg: DealRegistration,
    *,
    raise_with: list[str] | None,
    dismiss_with: list[str] | None,
    reason: str | None,
    actor: str,
    partial: bool = False,
) -> list[str]:
    """
    Apply the answer a save carried, or refuse it.

    raise_with    registrations to raise a conflict with ("same project")
    dismiss_with  registrations that are a different project; None means every
                  match not in raise_with — the save dialog's "Different
                  project…" answers for the rest at once
    reason        required whenever anything is dismissed
    partial       the Conflict tab answers ONE match at a time, so the others
                  are left unanswered instead of refusing the request

    Returns the ids of the conflicts raised. Runs after the registration's own
    values are applied and flushed, before commit — a refusal writes nothing.
    """
    matches = possible_matches(db, reg)
    by_id = {m.registration_id: m for m in matches}
    accounts = account_names(db)
    wanted = list(dict.fromkeys(raise_with or []))
    declined = list(dict.fromkeys(dismiss_with if dismiss_with is not None else []))

    for rid in wanted + declined:
        if rid not in by_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "NOT_A_POSSIBLE_CONFLICT",
                    "message": "That registration no longer looks like a match.",
                    "details": ["Reload the page and try again."],
                },
            )
    for rid in wanted:
        if by_id[rid].partner == reg.partner:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "SAME_PARTNER_NOT_A_CONFLICT",
                    "message": "Both registrations are from the same partner, so this is a duplicate, not a conflict.",
                    "details": ["Open the existing registration instead."],
                },
            )

    # A save that answers "different project" once answers it for every match it
    # did not raise. The Conflict tab answers one match at a time, so there an
    # unnamed match is simply left unanswered.
    if dismiss_with is None and not partial:
        declined = [rid for rid in by_id if rid not in wanted]
    undecided = [rid for rid in by_id if rid not in wanted and rid not in declined]
    reason = (reason or "").strip()

    if matches and (undecided and not partial or (declined and len(reason) < MIN_REASON)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "POSSIBLE_CONFLICT",
                "message": "A similar project is already registered at this End Client.",
                "details": [
                    "Same project: it's saved and a conflict is raised for review.",
                    "Different project: tell us why.",
                ],
                "matches": [match_row(m, reg, accounts) for m in matches],
            },
        )

    raised = [raise_conflict(db, by_id[rid], reg, actor=actor).conflict_id for rid in wanted]
    for rid in declined:
        _dismiss(db, reg, by_id[rid], reason, actor)
    return raised


# =========================================================================
# WHAT DEPENDS ON A REGISTRATION
# =========================================================================


def dependents_of(db: Session, reg: DealRegistration) -> dict[str, list[dict[str, str]]]:
    """The records that make deleting a registration unsafe, by name."""
    leads = {
        lead.lead_id: lead
        for lead in db.scalars(select(Lead).where(Lead.partner_deal_registration == reg.registration_id))
    }
    if reg.linked_lead and reg.linked_lead not in leads:
        lead = db.get(Lead, reg.linked_lead)
        if lead is not None:
            leads[lead.lead_id] = lead
    accounts = account_names(db)
    partner_of = partner_names_of_registrations(db, accounts)
    return {
        "leads": [
            {"id": lead_id, "name": lead.opportunity_name or "Untitled lead"}
            for lead_id, lead in sorted(leads.items())
        ],
        "conflicts": [
            {"id": c.conflict_id, "name": conflict_name(c, partner_of)} for c in conflicts_of(db, reg.registration_id)
        ],
    }

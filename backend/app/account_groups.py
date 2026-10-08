"""
Groups of companies, and the duplicate check on an Account save
(Release 1.1, decided 6 Oct 2026).

A GROUP is one level deep. Its head — usually the headquarters — has no Parent
Account; every other company of the group points straight at the head. There
are no chains, so "which group is this in" is one read: parent_account, or the
account itself when companies point at it.

The API keeps it flat; the person picking never has to know which company is
the head:
  · picking ANY company of a group as Parent Account files the account under
    that group's head;
  · a head given a Parent Account brings its companies along — the two groups
    become one, under the other group's head;
  · "Make this the head of the group" turns a member into the head: the old
    head and every other company then point at it.
  · a head that still has companies cannot be deleted.

"Group" is shown, never stored: a member reads its head's name, the head lists
its companies (GET /api/accounts/{id}/group).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .account_matching import Company, find_matches
from .audit import record_audit
from .changes import diff
from .messages import picked_record_missing, refusal
from .models import Account

#: Off only in the older test scripts, which make "Probe 1" and "Probe 2" side
#: by side — a module constant like requirements.ENFORCED, never configuration,
#: so nothing in production can switch it off. test_release_1_1.py turns it on.
CHECK_DUPLICATES = True


def members_of(db: Session, head_id: str) -> list[Account]:
    """The companies that point at this head, not the head itself."""
    return list(
        db.scalars(select(Account).where(Account.parent_account == head_id).order_by(Account.account_name))
    )


def head_of(account: Account) -> str:
    return account.parent_account or account.account_id


def _repoint(db: Session, account: Account, head: str | None, *, actor: str) -> None:
    was = account.parent_account
    if was == head:
        return
    account.parent_account = head
    record_audit(
        db,
        module="accounts",
        record_id=account.account_id,
        action="updated",
        actor=actor,
        changed_fields=["parent_account"],
        changed=diff({"parent_account": was}, {"parent_account": head}),
    )


def file_under_head(db: Session, account: Account, picked: str | None, *, actor: str) -> None:
    """
    Sets Parent Account from what was picked, kept one level deep. Runs on
    every save that sent parent_account — the value is already on the row,
    this decides what it should really be.
    """
    if not picked:
        account.parent_account = None
        return
    if picked == account.account_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "PARENT_IS_ITSELF",
                "A company can't be its own Parent Account.",
                ["Pick the head of its group, or any other company of it."],
            ),
        )
    parent = db.get(Account, picked)
    if parent is None:
        raise picked_record_missing("account")
    head = head_of(parent)
    if head == account.account_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "ALREADY_IN_THIS_GROUP",
                f"{parent.account_name} is already part of this company's group.",
                [f"To make it the head, open {parent.account_name} and choose Make head of group."],
            ),
        )
    account.parent_account = head
    # A head joining another group brings its companies with it — one level.
    for member in members_of(db, account.account_id):
        _repoint(db, member, head, actor=actor)


def make_head(db: Session, account: Account, *, actor: str) -> None:
    """This member becomes its group's head; the old head and the rest point at it."""
    old_head_id = account.parent_account
    if not old_head_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("ALREADY_HEAD", f"{account.account_name} isn't a member of a group, so there is nothing to change."),
        )
    old_head = db.get(Account, old_head_id)
    _repoint(db, account, None, actor=actor)
    for member in members_of(db, old_head_id):
        if member.account_id != account.account_id:
            _repoint(db, member, account.account_id, actor=actor)
    if old_head is not None:
        _repoint(db, old_head, account.account_id, actor=actor)


def group_rows(db: Session, account: Account) -> tuple[Account | None, list[Account]]:
    """(head, its companies) of the account's group; (None, []) when it has none."""
    head_id = head_of(account)
    head = account if head_id == account.account_id else db.get(Account, head_id)
    members = members_of(db, head_id)
    if head is None or not members:
        return None, []
    return head, members


def refuse_deleting_a_head(db: Session, account: Account) -> None:
    members = members_of(db, account.account_id)
    if members:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "ACCOUNT_HEADS_GROUP",
                f"This company is the head of a group of {len(members) + 1} companies, so it can't be deleted.",
                ["Open another company of the group and choose Make head of group first.", "Or deactivate it instead."],
            ),
        )


# --------------------------------------------------------------- duplicates

def _company(account: Account) -> Company:
    return Company(
        account_id=account.account_id,
        account_name=account.account_name or "",
        country=account.country,
        parent_account=account.parent_account,
        not_duplicate_of=tuple(account.not_duplicate_of or ()),
    )


def _match_row(db: Session, other: Account, names: dict[str, str], heads: set[str]) -> dict[str, Any]:
    head = head_of(other)
    return {
        "account_id": other.account_id,
        "account_name": other.account_name,
        "region": other.region,
        "country": other.country,
        "active": other.active,
        "account_type": sorted(t.account_type for t in other.types),
        "group_head": head if (other.parent_account or other.account_id in heads) else None,
        "group_name": names.get(head) if (other.parent_account or other.account_id in heads) else None,
    }


def guard_duplicate(db: Session, account: Account, *, different: bool) -> None:
    """
    Refuses a save that would duplicate a company already in Accounts — see
    app/account_matching.py for what counts. Runs on create, and on an update
    that changed the name or the Country. Call after the values and Parent
    Account are applied, before check_save.

    `different` is the "a different company" answer, sent with THIS save: it
    settles every similar name found now, and is remembered against them
    (not_duplicate_of). An exact match is refused whatever the answer.
    """
    if not CHECK_DUPLICATES:
        return
    db.flush()
    everyone = list(db.scalars(select(Account)))
    heads = {a.parent_account for a in everyone if a.parent_account}
    names = {a.account_id: a.account_name for a in everyone}
    own_group = {head_of(account)}
    if account.account_id in heads:
        own_group.add(account.account_id)

    found = find_matches(_company(account), [_company(a) for a in everyone], group_heads=own_group)
    by_id = {a.account_id: a for a in everyone}

    if found.exact is not None:
        other = by_id[found.exact.account_id]
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "ACCOUNT_EXISTS",
                "This company is already in Accounts.",
                ["It has the same registered name, in the same Country.", "Open it instead of adding it again."],
                existing=_match_row(db, other, names, heads),
            ),
        )
    if not found.similar:
        return
    if different:
        account.not_duplicate_of = sorted(set(account.not_duplicate_of or []) | {c.account_id for c in found.similar})
        return
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal(
            "POSSIBLE_DUPLICATE_ACCOUNT",
            "A company with a similar name is already in Accounts.",
            [
                "Same company: open it instead.",
                "Same group in another country: add it to that group.",
                "Different company: save it on its own.",
            ],
            matches=[_match_row(db, by_id[c.account_id], names, heads) for c in found.similar[:8]],
        ),
    )

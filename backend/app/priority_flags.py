"""
Low Hanging and Top 10 — the two capped, ranked Opportunity picks.

Mirrors frontend/src/lib/priorityFlags.ts exactly, on purpose: this is
Opportunity business logic (a 5/10 cap, mutual exclusivity, a rank the user
picks rather than one the system assigns), not plumbing, so both sides agree
on the same rule rather than one trusting the other. The frontend still
enforces it too — this module is what makes that enforcement real once the
request no longer passes through MSW.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PriorityFlag:
    flag: str
    rank: str
    cap: int
    label: str


PRIORITY_FLAGS: tuple[PriorityFlag, ...] = (
    PriorityFlag("is_low_hanging", "low_hanging_rank", 5, "Low Hanging"),
    PriorityFlag("is_top_10", "top_10_rank", 10, "Top 10"),
)


class PriorityFlagError(ValueError):
    """Raised with a user-facing message — the router turns this into a 409."""


def resolve_priority_flag_patch(
    all_opportunities: Sequence[Mapping[str, object]],
    current_id: str,
    current: Mapping[str, object] | None,
    patch: Mapping[str, object],
) -> dict[str, object]:
    """
    Validates and enriches one write against the priority-flag rules.

    Only looks at flags actually present in `patch` — a save that never
    touches is_low_hanging or is_top_10 comes back unchanged. The chosen rank
    must already be in `patch` too: this never assigns one, only checks it.

    Returns the patch with is_low_hanging/is_top_10's rank fields filled in
    (on a real pick) or cleared (on an uncheck), and the OTHER flag/rank pair
    cleared when one is freshly picked, since the two are mutually exclusive.
    Raises PriorityFlagError, with a message safe to show the user, when the
    requested rank is missing, out of range, or already held by another row.
    """
    out: dict[str, object] = dict(patch)

    for pf in PRIORITY_FLAGS:
        if pf.flag not in patch:
            continue

        turning_on = bool(patch[pf.flag])
        was_on = bool(current.get(pf.flag)) if current is not None else False

        if turning_on:
            requested = patch.get(pf.rank)
            if not isinstance(requested, int) or isinstance(requested, bool):
                raise PriorityFlagError(f"Pick a rank between 1 and {pf.cap} for {pf.label}.")
            if not (1 <= requested <= pf.cap):
                raise PriorityFlagError(f"Pick a rank between 1 and {pf.cap} for {pf.label}.")

            taken = {
                row.get(pf.rank)
                for row in all_opportunities
                if row.get("id") != current_id and row.get(pf.flag)
            }
            if requested in taken:
                raise PriorityFlagError(
                    f"{pf.label} rank {requested} is already taken — pick another open rank."
                )
            out[pf.rank] = requested

            # Mutually exclusive: picking one clears the other.
            for other in PRIORITY_FLAGS:
                if other.flag == pf.flag:
                    continue
                out[other.flag] = False
                out[other.rank] = None
        elif not turning_on and was_on:
            out[pf.rank] = None

    return out


def resolve_reorder(
    all_opportunities: Sequence[Mapping[str, object]],
    flag: str,
    ranks: Mapping[str, object],
) -> dict[str, tuple[int | None, int]]:
    """
    New ranks for picks ALREADY on one list, set together — a drag on the Low
    Hanging / Top 10 screen (Release 1.2, 15 Oct 2026). A swap is two moves at
    once; one at a time, the first would land on a rank the second still holds.

    Returns {id: (old rank, new rank)} for the picks that move. Raises
    PriorityFlagError when the flag is unknown, an id is not on that list, a
    rank is out of range, or the list would end with two picks on one rank.
    It never adds to or takes off the list — that is the record's own save.
    """
    pf = next((p for p in PRIORITY_FLAGS if p.flag == flag), None)
    if pf is None:
        raise PriorityFlagError("That list doesn't exist.")
    on_list = {row.get("id"): row.get(pf.rank) for row in all_opportunities if row.get(pf.flag)}
    moves: dict[str, tuple[int | None, int]] = {}
    for opp_id, rank in ranks.items():
        if opp_id not in on_list:
            raise PriorityFlagError(f"That opportunity isn't on {pf.label} any more. Reload the page.")
        if not isinstance(rank, int) or isinstance(rank, bool) or not (1 <= rank <= pf.cap):
            raise PriorityFlagError(f"Pick a rank between 1 and {pf.cap} for {pf.label}.")
        if on_list[opp_id] != rank:
            moves[opp_id] = (on_list[opp_id], rank)  # type: ignore[assignment]
    final = {**on_list, **{opp_id: new for opp_id, (_, new) in moves.items()}}
    held = [r for r in final.values() if r is not None]
    if len(held) != len(set(held)):
        raise PriorityFlagError(f"Two picks can't share a rank on {pf.label}. Reload the page and try again.")
    return moves

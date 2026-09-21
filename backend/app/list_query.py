"""
The list contract every pipeline list endpoint serves — one implementation.

    GET /api/leads?lead_status=OPEN&lead_status=ON_HOLD      equality, repeated = OR
                  &segment_ne=GOVERNMENT                     isn't any of
                  &estimated_value_gte=100000                range, inclusive (_lt/_gt strict)
                  &opportunity_name_contains=metro           text: _is _isnt _contains _ncontains _starts
                  &parent_deal_empty=1                       is empty (1) / is not empty (0)
                  &revenue.usd_gte=250000                    …through one dot
                  &expected_close_month_lte=2026-12
                  &q=metro&_search=opportunity_name,end_client
                  &_sort=estimated_value&_order=desc
                  &_page=1&_limit=25                         total on X-Total-Count

Leads, Opportunities and Deals each carried their own copy of this loop, and
all three sorted every column as TEXT — "100000" before "20000" — so a list
sorted by value was quietly wrong. The List and Kanban views share one filter
bar (UX roadmap, 17 Sep 2026), which makes ranges part of the contract too;
adding them three times would have been three places to drift.

Rows are already serialised (lookups joined under `__labels`), so a filter
compares what the row holds and search/sort read what a person sees. The text
operators read what a person sees too — a lookup's name, not its id.

An operator is a SUFFIX, so a real field whose name happens to end in one
(`something_is`) must still filter by equality: a key that some row carries is
always a field, never field + operator.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from starlette.datastructures import QueryParams

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}
RANGE_SUFFIXES = ("_gte", "_lte", "_gt", "_lt")
TEXT_SUFFIXES = ("_isnt", "_is", "_ncontains", "_contains", "_starts")
#: Longest first, so `_ncontains` is not read as `_contains`.
OPERATOR_SUFFIXES = tuple(sorted((*RANGE_SUFFIXES, *TEXT_SUFFIXES, "_ne", "_empty"), key=len, reverse=True))


def _value(row: dict, field: str) -> Any:
    """A row value by name, or through one dot into a nested object — `revenue.usd`."""
    head, _, rest = field.partition(".")
    value = row.get(head)
    return value.get(rest) if rest and isinstance(value, dict) else (None if rest else value)


def _display(row: dict, field: str, lookups: set[str]) -> str:
    if field in lookups:
        label = (row.get("__labels") or {}).get(field)
        if label:
            return str(label)
    value = _value(row, field)
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return "" if value is None else str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _comparable(value: Any) -> tuple[int, Any] | None:
    """(0, number) or (1, text) — numbers compare as numbers, everything else as ISO-ish text."""
    if value is None or value == "":
        return None
    number = _number(value)
    if number is not None:
        return (0, number)
    if isinstance(value, (date, datetime)):
        return (1, value.isoformat())
    return (1, str(value))


def _matches(value: Any, wanted: set[str]) -> bool:
    if isinstance(value, list):
        return any(str(v) in wanted for v in value)
    return str(value if value is not None else "") in wanted


def _in_range(value: Any, bound: str, suffix: str) -> bool:
    have, limit = _comparable(value), _comparable(bound)
    if limit is None:
        return True
    if have is None or have[0] != limit[0]:
        return False  # a blank value is outside every range
    return {
        "_gte": have[1] >= limit[1],
        "_lte": have[1] <= limit[1],
        "_gt": have[1] > limit[1],
        "_lt": have[1] < limit[1],
    }[suffix]


def _text_matches(shown: str, wanted: list[str], suffix: str) -> bool:
    """Case-insensitive, against what a person sees. Repeated values OR together; a negative ANDs."""
    have = shown.strip().lower()
    wants = [w.strip().lower() for w in wanted if w.strip()]
    if not wants:
        return True
    if suffix == "_is":
        return have in wants
    if suffix == "_isnt":
        return have not in wants
    if suffix == "_contains":
        return any(w in have for w in wants)
    if suffix == "_ncontains":
        return not any(w in have for w in wants)
    return any(have.startswith(w) for w in wants)  # _starts


def _operator_of(key: str, known: set[str]) -> tuple[str, str | None]:
    """(field, operator suffix or None). A key some row carries is a field, never field + suffix."""
    if key in known:
        return key, None
    for suffix in OPERATOR_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)], suffix
    return key, None


def _sort_key(row: dict, field: str, lookups: set[str]):
    if field not in lookups:
        number = _number(_value(row, field))
        if number is not None:
            return (0, number, "")
    return (1, 0, _display(row, field, lookups).lower())


def _is_blank(row: dict, field: str, lookups: set[str]) -> bool:
    return _display(row, field, lookups) == ""


def _shown(row: dict, field: str, lookups: set[str]) -> str:
    """
    What a text operator compares. A checkbox reads true/false, so "is Yes" is
    `_is=true` and "is No" is `_isnt=true` — which also holds a never-ticked box.
    """
    value = _value(row, field)
    if isinstance(value, bool):
        return "true" if value else "false"
    return _display(row, field, lookups)


def run_list_query(
    rows: list[dict],
    params: QueryParams,
    *,
    lookups: Iterable[str],
    default_search: Iterable[str],
) -> tuple[list[dict], int]:
    lookup_set = set(lookups)

    known = {k for r in rows for k in r}
    for key in {k for k in params if k not in RESERVED}:
        field, suffix = _operator_of(key, known)
        if suffix in RANGE_SUFFIXES:
            bound = params.get(key)
            rows = [r for r in rows if _in_range(_value(r, field), bound, suffix)]
        elif suffix in TEXT_SUFFIXES:
            wanted = params.getlist(key)
            rows = [r for r in rows if _text_matches(_shown(r, field, lookup_set), wanted, suffix)]
        elif suffix == "_ne":
            unwanted = set(params.getlist(key))
            rows = [r for r in rows if not _matches(_value(r, field), unwanted)]
        elif suffix == "_empty":
            blank = params.get(key) not in ("0", "false")
            rows = [r for r in rows if _is_blank(r, field, lookup_set) == blank]
        else:
            wanted = set(params.getlist(key))
            rows = [r for r in rows if _matches(_value(r, key), wanted)]

    q = (params.get("q") or "").strip().lower()
    if q:
        named = [f for f in (params.get("_search") or "").split(",") if f]
        fields = named or list(default_search)
        rows = [r for r in rows if q in " ".join(_display(r, f, lookup_set) for f in fields).lower()]

    sort = params.get("_sort")
    if sort:
        # Blank values sit at the end in BOTH directions — a descending sort by
        # value should open on the biggest pursuit, not on the unpriced ones.
        filled = [r for r in rows if not _is_blank(r, sort, lookup_set)]
        blank = [r for r in rows if _is_blank(r, sort, lookup_set)]
        filled.sort(key=lambda r: _sort_key(r, sort, lookup_set), reverse=params.get("_order") == "desc")
        rows = filled + blank

    total = len(rows)
    page = int(params.get("_page") or 0)
    limit = int(params.get("_limit") or 0)
    if page > 0 and limit > 0:
        rows = rows[(page - 1) * limit : page * limit]
    return rows, total

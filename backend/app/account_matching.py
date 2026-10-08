"""
Is this company already in Accounts? (Release 1.1, decided 6 Oct 2026.)

An Account Name is the company's REGISTERED name in its country — "Astrikos
Inc", never "Astrikos USA" — so two rules decide it:

  · the same registered name in the same Country is the same company. The save
    is refused, and the screen opens the one already there (ACCOUNT_EXISTS);
  · a similar name — the same name in another Country, another legal form of
    it, a typo — is ASKED about (POSSIBLE_DUPLICATE_ACCOUNT): the same company
    (open it), part of its group (Parent Account), or a different company
    (one click, decided 7 Oct 2026 — no reason is asked).

"The same registered name" ignores case, punctuation and how the legal form is
spelt: "Astrikos AI Pvt. Ltd." and "ASTRIKOS AI PRIVATE LIMITED" are one name.
"Similar" compares the name WITHOUT its legal form ("astrikos ai"), see
similar() for the exact rule.

Companies already in the account's own group are never asked about — they are
meant to share a name. Neither is an account a "different company" answer was
already given about (accounts.not_duplicate_of, read both ways).

No company name and no list of "common words" is written here (decided 7 Oct
2026): the one vocabulary is LEGAL_FORMS, the words that say what kind of
company it is — Pvt, Ltd, Inc, LLC — never which one.

Pure functions over rows, no request state: the API, Import and the
production report (release_1_1_duplicate_accounts.py) share them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

#: Spellings of one legal form, to the one used for comparing.
LEGAL_SPELLINGS = {
    "limited": "ltd",
    "private": "pvt",
    "incorporated": "inc",
    "corporation": "corp",
    "company": "co",
    "l l c": "llc",
}

#: Words that say what kind of company it is, not which one.
LEGAL_FORMS = {
    "pvt", "ltd", "inc", "llc", "llp", "plc", "corp", "co", "gmbh", "ag", "sa", "nv", "bv", "spa", "srl",
    "sarl", "pte", "pty", "fze", "fzco", "fz", "fzllc", "fzc", "wll", "pjsc", "psc", "jsc", "kk", "oy", "ab",
    "as", "opc", "lp",
}

#: Two names this alike (0–1, difflib) are a typo apart.
TYPO_RATIO = 0.85

#: A name shorter than this is never taken as the start of another.
MIN_PREFIX = 3


def _words(name: str | None) -> list[str]:
    text = (name or "").lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for spelt, form in LEGAL_SPELLINGS.items():
        text = re.sub(rf"\b{spelt}\b", form, text)
    return [w for w in text.split(" ") if w and w != "and"]


def registered_name(name: str | None) -> str:
    """The name as compared for "the same registered name"."""
    return " ".join(_words(name))


def core_name(name: str | None) -> str:
    """The name without its legal form — "astrikos ai" for Astrikos AI Pvt. Ltd."""
    words = _words(name)
    while words and words[-1] in LEGAL_FORMS:
        words.pop()
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def similar(a: str | None, b: str | None) -> bool:
    """
    Two names worth asking about, both without their legal form:
      · the same name (Astrikos Inc / Astrikos LLC);
      · a typo apart (Astrikos / Astrikkos);
      · one is the start of the other, in whole words (Astrikos Inc /
        Astrikos AI Pvt Ltd). Saudi Aramco and Saudi Electricity are not
        asked: neither name is the start of the other.
    """
    ca, cb = core_name(a), core_name(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    if SequenceMatcher(None, ca, cb).ratio() >= TYPO_RATIO:
        return True
    short, long_ = sorted((ca, cb), key=len)
    return len(short) >= MIN_PREFIX and long_.startswith(short + " ")


@dataclass(frozen=True)
class Company:
    """What matching reads of an account."""

    account_id: str
    account_name: str
    country: str | None
    parent_account: str | None
    not_duplicate_of: tuple[str, ...] = ()

    @property
    def head(self) -> str:
        return self.parent_account or self.account_id


@dataclass
class Matches:
    exact: Company | None
    similar: list[Company]


def find_matches(candidate: Company, others: Iterable[Company], *, group_heads: set[str] | None = None) -> Matches:
    """
    The accounts `candidate` would duplicate.

    `group_heads` names the heads whose groups the candidate belongs to (its own
    head, and itself when other companies point at it) — their companies are
    never asked about. Exact matches are refused even inside a group: two
    accounts with one registered name in one Country are one company.
    """
    group_heads = group_heads or {candidate.head}
    name = registered_name(candidate.account_name)
    exact: Company | None = None
    alike: list[Company] = []
    for other in others:
        if other.account_id == candidate.account_id:
            continue
        if (
            candidate.country
            and other.country == candidate.country
            and registered_name(other.account_name) == name
        ):
            exact = exact or other
            continue
        if other.head in group_heads:
            continue
        if other.account_id in candidate.not_duplicate_of or candidate.account_id in other.not_duplicate_of:
            continue
        if similar(candidate.account_name, other.account_name):
            alike.append(other)
    alike.sort(key=lambda c: (core_name(c.account_name) != core_name(candidate.account_name), c.account_name.lower()))
    return Matches(exact=exact, similar=alike)

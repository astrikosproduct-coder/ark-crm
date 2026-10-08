"""
The fiscal year — one setting, and every calendar rule that follows from it.

THE SETTING
-----------
FISCAL_YEAR_START_MONTH, 1-12, read once from the environment at start-up.
Default 4: the fiscal year runs April to March (decided 15 Sep 2026). Nothing
else in the application may name a month: the dashboard's quarter presets,
sales targets' fiscal year, and any cumulative figure that resets at year start
all ask this module.

Setup lists a Fiscal Year item (Zoho's place for it) that is not built. When it
is, the value moves into the database and `_configured_start_month` is the one
function that changes.

CHANGING IT IS NOT FREE. sales_targets stores the fiscal year label beside each
month, because targets are set and locked per year. Change the start month
after targets exist and those labels describe the old year; re-label them
deliberately before restarting with a new value.

NAMING
------
A fiscal year is named by the calendar year it ENDS in, two digits: with an
April start, FY27 runs 01 Apr 2026 to 31 Mar 2027. With a January start the
fiscal year is the calendar year, so FY27 is Jan-Dec 2027.

Quarters count from the start month: with April, Q1 Apr-Jun, Q2 Jul-Sep,
Q3 Oct-Dec, Q4 Jan-Mar.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta

DEFAULT_START_MONTH = 4

_LABEL = re.compile(r"^FY(\d{2})$")


def _configured_start_month() -> int:
    raw = os.getenv("FISCAL_YEAR_START_MONTH", "").strip()
    if not raw:
        return DEFAULT_START_MONTH
    if not raw.isdigit() or not 1 <= int(raw) <= 12:
        # Refuse to start rather than bucket a year of figures on a guessed month.
        raise ValueError(f"FISCAL_YEAR_START_MONTH must be a month number, 1 to 12 — got {raw!r}")
    return int(raw)


#: The month the fiscal year starts in. The ONE place this is decided.
FISCAL_YEAR_START_MONTH = _configured_start_month()


def add_months(day: date, months: int) -> date:
    """The first of the month `months` after `day`'s month (negative goes back)."""
    index = day.month - 1 + months
    return date(day.year + index // 12, index % 12 + 1, 1)


def start_year_of(day: date) -> int:
    """The calendar year the fiscal year holding `day` STARTS in."""
    return day.year if day.month >= FISCAL_YEAR_START_MONTH else day.year - 1


def fiscal_year_of(day: date) -> int:
    """The calendar year the fiscal year holding `day` ENDS in — its name. 01 Apr 2026 -> 2027."""
    start_year = start_year_of(day)
    return start_year if FISCAL_YEAR_START_MONTH == 1 else start_year + 1


def label_of(day: date) -> str:
    """'FY27' for any day from 01 Apr 2026 to 31 Mar 2027 (with an April start)."""
    return f"FY{fiscal_year_of(day) % 100:02d}"


def parse_label(label: str) -> int:
    """'FY27' -> 2027. Two digits, this century — the only years this CRM will see."""
    match = _LABEL.match(label or "")
    if not match:
        raise ValueError(f"Not a fiscal year: {label!r}. Write it as FY27.")
    return 2000 + int(match.group(1))


def first_day(label: str) -> date:
    """The day a fiscal year starts. FY27 -> 01 Apr 2026."""
    end_year = parse_label(label)
    start_year = end_year if FISCAL_YEAR_START_MONTH == 1 else end_year - 1
    return date(start_year, FISCAL_YEAR_START_MONTH, 1)


def last_day(label: str) -> date:
    """The day a fiscal year ends. FY27 -> 31 Mar 2027."""
    return add_months(first_day(label), 12) - timedelta(days=1)


def months_of(label: str) -> list[date]:
    """The twelve months of a fiscal year, each as its 1st, in order."""
    first = first_day(label)
    return [add_months(first, i) for i in range(12)]


def month_number(day: date) -> int:
    """1 for the fiscal year's first month, 12 for its last. April -> 1."""
    return (day.month - FISCAL_YEAR_START_MONTH) % 12 + 1


def quarter_number(day: date) -> int:
    """1-4. With an April start, Q1 is Apr-Jun."""
    return (month_number(day) - 1) // 3 + 1


def quarter_bounds(day: date) -> tuple[date, date]:
    """(first day, last day) of the fiscal quarter holding `day`."""
    start = add_months(date(start_year_of(day), FISCAL_YEAR_START_MONTH, 1), (quarter_number(day) - 1) * 3)
    return start, add_months(start, 3) - timedelta(days=1)

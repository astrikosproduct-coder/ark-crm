"""
The company clock.

TWO KINDS OF TIME, AND THEY ARE NOT THE SAME
--------------------------------------------
An INSTANT is a moment that happened — a save, a stage move, a sign-in. It is
stored as `timestamptz` in UTC and is the same instant for everyone; Dubai,
Houston and Bengaluru merely print it differently.

A CALENDAR FACT is a day — a contract signed date, an expected close month. It
is stored as `Date`, carries no zone, and must NEVER be converted: a contract
signed on 30 Sep was signed on 30 Sep in every country on earth.

Nothing here converts a calendar fact. This module exists for the third thing,
which is where the two meet: ANSWERING "WHICH DAY DID THIS INSTANT FALL ON".
Days in stage, days since last update, and every future aging or SLA bucket ask
that question, and the answer depends on whose calendar you ask.

Before this module the answer was UTC on the server and the viewer's own zone in
the browser, so a card could read "12 days in stage" while a server-computed
value said 11 and nobody could ever work out why. One clock, declared once,
removes the disagreement: the server counts days in company time, the frontend
formats and counts in company time (src/lib/time.ts holds the same constant),
and two people looking at one record see one number.

WHAT THIS DOES NOT CHANGE
-------------------------
Elapsed time. A 48-hour SLA is a duration between two stored instants, and a
duration is timezone-independent by construction — rendering it in IST cannot
make it longer or shorter for a BD in Houston. Only calendar-worded rules
("by end of day", "within 2 business days") would depend on the zone, and the
right place to resolve those is policy, not code. Never derive an SLA from a
formatted date; always subtract the instants.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

#: Astrikos HQ. The one clock the whole application reckons days in.
#: Mirrored in src/lib/time.ts — change both together.
COMPANY_TZ = ZoneInfo("Asia/Kolkata")

COMPANY_TZ_LABEL = "IST"


def now_utc() -> datetime:
    """The instant, always UTC. What every timestamp column is stamped with."""
    return datetime.now(timezone.utc)


def today_company() -> date:
    """Today's date on the company calendar — never the server's local one."""
    return datetime.now(COMPANY_TZ).date()


def company_date_of(moment: datetime | None) -> date | None:
    """
    Which company-calendar day an instant fell on.

    A naive datetime is read as UTC rather than as company time: every naive
    value reaching this application came out of a `timestamptz` column, and
    guessing the local zone of a value that never had one is how off-by-one-day
    bugs are born.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(COMPANY_TZ).date()


def days_since(moment: datetime | None) -> int | None:
    """
    Whole company-calendar days between an instant and today, floored at 0.

    Calendar days, not elapsed/24 — "days in stage" counts date boundaries
    crossed, which is what a BD means by it and what the frontend's own
    differenceInCalendarDays agrees with.
    """
    day = company_date_of(moment)
    if day is None:
        return None
    return max(0, (today_company() - day).days)

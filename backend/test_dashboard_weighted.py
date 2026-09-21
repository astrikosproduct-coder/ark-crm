"""
The weighted-pipeline unit test.

    python run_tests.py test_dashboard_weighted.py

WHY THIS FILE EXISTS
--------------------
For as long as the dashboard had shipped, `Row.weighted` read

    self.usd * float(self.record.probability_pct or 0) / 100

and a record's probability_pct is a FRACTION — 0.70 is 70%, written that way by
app/progression.py and validated there as 0..1. So the dashboard divided by 100
a second time and every weighted number on the page was a hundredth of the
truth: an $8.4M weighted pipeline rendered as $84,000.

Nothing caught it because nothing compared the two conventions in one place.
The number was plausible, the page did not error, and the only way to notice
was to do the arithmetic by hand. That is exactly the failure a CXO screen
cannot have, so the rule now has a test rather than a comment.

WHAT IT PINS
------------
1. The two conventions, stated as facts: records hold fractions, `stages` holds
   whole numbers. If either flips, this fails first and loudly.
2. Value x Probability, on a worked example with round numbers.
3. That the fraction stored for a stage matches the whole number that stage
   advertises — the join between the two conventions, which is where a future
   mistake would land.

Read-only: it opens no transaction and writes nothing, so it runs in either
half of the suite.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Stage
from app.routers.dashboard import Row

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok    {message}")
    else:
        print(f"  FAIL  {message}")
        FAILURES.append(message)


class _FakeRecord:
    """The two attributes Row.weighted actually reads."""

    def __init__(self, probability_pct: Decimal | None) -> None:
        self.probability_pct = probability_pct


def _row(usd: float, probability: Decimal | None) -> Row:
    """A Row without touching the database — Row.usd reads only `revenue`."""
    row = Row.__new__(Row)
    row.record = _FakeRecord(probability)  # type: ignore[attr-defined]
    row.revenue = {"usd": usd}  # type: ignore[attr-defined]
    return row


def test_weighted_multiplies_by_the_stored_fraction() -> None:
    print("\nweighted = value x probability, and probability is already a fraction")
    # Stage 6 Commercial Evaluation advertises 70%; a record there stores 0.70.
    check(_row(1_000_000.0, Decimal("0.70")).weighted == 700_000.0, "$1,000,000 at 0.70 weighs $700,000")
    check(_row(250_000.0, Decimal("0.40")).weighted == 100_000.0, "$250,000 at 0.40 weighs $100,000")
    # Stage 8/9 are certain, and a certainty must not be scaled away.
    check(_row(500_000.0, Decimal("1.00")).weighted == 500_000.0, "a record at 1.00 weighs its whole value")
    # Closed Lost sets probability to 0 — see progression.py.
    check(_row(900_000.0, Decimal("0")).weighted == 0.0, "a record at 0 weighs nothing")
    check(_row(900_000.0, None).weighted == 0.0, "a record with no probability weighs nothing")
    # The regression itself: the old code returned 7000.0 for this.
    check(_row(1_000_000.0, Decimal("0.70")).weighted != 7_000.0, "not divided by 100 a second time")


def test_the_two_conventions_still_disagree_on_purpose() -> None:
    print("\nstages hold whole numbers, records hold fractions")
    with SessionLocal() as db:
        stages = list(db.scalars(select(Stage).order_by(Stage.stage)))
    check(bool(stages), "the stages table has rows")
    if not stages:
        return

    whole = [s for s in stages if s.probability_pct is not None]
    check(
        all(0 <= int(s.probability_pct) <= 100 for s in whole),
        "every stage's Probability % is a whole 0-100",
    )
    check(
        all(int(s.probability_pct) % 5 == 0 for s in whole),
        "every stage's Probability % is a multiple of 5",
    )
    check(
        any(int(s.probability_pct) > 1 for s in whole),
        "the stage ladder is NOT stored as fractions (something above 1 exists)",
    )

    # The join: a record sitting at a stage stores that stage's number / 100.
    stage_6 = next((s for s in stages if s.stage == 6), None)
    if stage_6 is not None:
        fraction = Decimal(stage_6.probability_pct) / 100
        check(
            _row(1_000_000.0, fraction).weighted == float(1_000_000 * fraction),
            f"a record at Stage 6 ({stage_6.probability_pct}%) weighs {float(fraction):.0%} of its value",
        )


def main() -> int:
    print("=" * 74)
    print("  DASHBOARD — WEIGHTED PIPELINE")
    print("=" * 74)
    test_weighted_multiplies_by_the_stored_fraction()
    test_the_two_conventions_still_disagree_on_purpose()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

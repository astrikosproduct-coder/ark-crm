"""
/api/clock — the server's time, for the clock in the top bar.

    GET /api/clock    any signed-in user

The instant is app/clock.py::now_utc — the same clock every created, modified
and audit timestamp is stamped with — and `today` is the company-calendar day
it falls on. The browser shows this, never the laptop's own clock, so a wrong
laptop clock cannot make the screen disagree with what the server records.
Also what tells an open dashboard that the day (and so the quarter or fiscal
year) has turned.
"""

from typing import Any

from fastapi import APIRouter

from ..clock import COMPANY_TZ, COMPANY_TZ_LABEL, now_utc, today_company

router = APIRouter(tags=["clock"])


@router.get("/clock")
def server_clock() -> dict[str, Any]:
    return {
        "now": now_utc(),
        "today": today_company(),
        "timezone": COMPANY_TZ.key,
        "timezone_label": COMPANY_TZ_LABEL,
    }

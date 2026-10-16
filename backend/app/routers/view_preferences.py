"""
/api/view-preferences/{view_key} — one person's own list columns or Kanban board.

    GET     the caller's settings for this view, or {"settings": null} (the default view)
            view keys: list:<list>, kanban:<module>, page:<module> (the view a page opens on)
    PUT     replace them
    DELETE  back to the default view

Release 1.2 (14 Oct 2026). Always the CALLER's: identity comes from the session
and nothing in the path or body can name another person, so Kishan's ten
columns never reach Amit's list. The settings are a layout, not data; the
browser reads them against the published register and drops any field that is
no longer there. Shape and size are checked here so a broken page cannot store
anything else.
"""

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user
from ..clock import now_utc
from ..database import get_db
from ..messages import refusal
from ..models import User, UserViewPreference

router = APIRouter(tags=["view-preferences"])

VIEW_KEY = re.compile(r"^(list|kanban|page):[a-z_]+$")
VIEW_NAME = re.compile(r"^[a-z0-9_-]{1,40}$")
API_NAME = re.compile(r"^[A-Za-z0-9_—\-]{1,120}$")
MAX_BYTES = 8_000
MAX_FIELDS = 60

#: What each kind of view may hold, and the type of each.
LIST_KEYS = {"columns": list, "widths": dict, "page_size": int, "wrap": bool, "pinned": list}
KANBAN_KEYS = {"categorize_by": str, "aggregate_by": str, "card_fields": list}
#: A module's page: the view it opens on for this person (List, Kanban, Top 10…).
PAGE_KEYS = {"default_view": str}
PAGE_SIZES = {10, 25, 50, 100}
AGGREGATES = {"none", "value", "weighted"}


class ViewSettings(BaseModel):
    settings: dict[str, Any]


def _refuse(why: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal("VIEW_SETTINGS_INVALID", "These view settings can't be saved.", [why, "Reload the page and try again."]),
    )


def _check(view_key: str, settings: dict[str, Any]) -> dict[str, Any]:
    if not VIEW_KEY.match(view_key):
        raise _refuse("That view doesn't exist.")
    if len(json.dumps(settings)) > MAX_BYTES:
        raise _refuse("The settings are too large.")
    allowed = LIST_KEYS if view_key.startswith("list:") else KANBAN_KEYS if view_key.startswith("kanban:") else PAGE_KEYS
    for key, value in settings.items():
        kind = allowed.get(key)
        if kind is None:
            raise _refuse(f"“{key}” isn't a setting of this view.")
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise _refuse(f"“{key}” has the wrong shape.")
    names = [
        *settings.get("columns", []),
        *settings.get("pinned", []),
        *settings.get("card_fields", []),
        *settings.get("widths", {}).keys(),
    ]
    if any(not isinstance(n, str) or not API_NAME.match(n) for n in names) or len(names) > 4 * MAX_FIELDS:
        raise _refuse("A column isn't a field name.")
    if any(not isinstance(w, int) or isinstance(w, bool) or not 60 <= w <= 800 for w in settings.get("widths", {}).values()):
        raise _refuse("A column width is out of range.")
    if "page_size" in settings and settings["page_size"] not in PAGE_SIZES:
        raise _refuse("Rows per page is 10, 25, 50 or 100.")
    if "aggregate_by" in settings and settings["aggregate_by"] not in AGGREGATES:
        raise _refuse("A board totals nothing, Value or Weighted value.")
    if "default_view" in settings and not VIEW_NAME.match(settings["default_view"]):
        raise _refuse("That view doesn't exist.")
    if "categorize_by" in settings and not API_NAME.match(settings["categorize_by"]):
        raise _refuse("Categorize By isn't a field name.")
    return settings


@router.get("/view-preferences/{view_key}")
def get_view_preference(view_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(UserViewPreference, (user.user_id, view_key))
    return {"settings": row.settings if row is not None else None}


@router.put("/view-preferences/{view_key}", response_model=ViewSettings)
def put_view_preference(
    view_key: str, payload: ViewSettings, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    settings = _check(view_key, payload.settings)
    row = db.get(UserViewPreference, (user.user_id, view_key))
    if row is None:
        row = UserViewPreference(user_id=user.user_id, view_key=view_key, settings=settings)
        db.add(row)
    else:
        row.settings = settings
        row.updated_at = now_utc()
    db.commit()
    return {"settings": row.settings}


@router.delete("/view-preferences/{view_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_view_preference(view_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(UserViewPreference, (user.user_id, view_key))
    if row is not None:
        db.delete(row)
        db.commit()

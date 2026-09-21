"""
The words a person reads when the server says no.

Every refusal is ``{"code", "message", "details"?}``:

* ``code``    — what the frontend and the tests branch on. Never shown.
* ``message`` — ONE short sentence saying what happened.
* ``details`` — optional bullets, one idea each, usually the way forward.

The wording rules (CLAUDE.md, "Dialog and message copy"): no record ids, no
api_names, no internal words ("read-through", "custom_fields", "per-stage");
say what went wrong and the one action that fixes it. The frontend renders
message + details through one component, so a sentence written here reads the
same on every screen that shows it — which is why the wording lives here and
not in a lookup table on the client, where it would drift from the rule it
describes.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


def refusal(code: str, message: str, details: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    body.update(extra)
    return body


def not_found(noun: str, **extra: Any) -> HTTPException:
    """A record that is not there — deleted by someone else, or a stale link."""
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        refusal("NOT_FOUND", f"This {noun} no longer exists. It may have been deleted.", **extra),
    )


def already_exists(**extra: Any) -> HTTPException:
    """An id collision on create — two saves racing for the same next number."""
    return HTTPException(
        status.HTTP_409_CONFLICT,
        refusal("ALREADY_EXISTS", "Someone saved at the same moment. Reload the page and try again.", **extra),
    )


def picked_record_missing(noun: str, **extra: Any) -> HTTPException:
    """A lookup value naming a record that no longer exists."""
    article = "an" if noun[:1].lower() in "aeiou" else "a"
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal(
            "PICKED_RECORD_MISSING",
            f"The {noun} you picked no longer exists.",
            [f"Pick {article} {noun} again, then save."],
            **extra,
        ),
    )


#: The form was built from a register that has since changed — a field removed
#: or renamed in Administration while the page stayed open.
FORM_OUT_OF_DATE = "This form is out of date. Reload the page and try again. Nothing was saved."

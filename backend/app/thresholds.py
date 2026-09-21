"""
Min value / Max value, enforced where a record is written.

The form refuses an out-of-range number too, but that is presentation. This is
the boundary: a direct API call with Relationship Score 11 is refused here
whatever the browser did.

Read from the register (field_definitions.min_value / max_value) on every
write, so a threshold changed in Administration applies to the next save with
no code change. Both bounds are inclusive; null means no bound on that side.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import FieldDefinition, FieldPlacement


def _format(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def _range_text(low: float | None, high: float | None) -> str:
    if low is not None and high is not None:
        return f"between {_format(low)} and {_format(high)}"
    if low is not None:
        return f"at least {_format(low)}"
    return f"at most {_format(high)}"


def check_thresholds(db: Session, module: str, values: dict[str, Any]) -> None:
    """422 when any value in `values` falls outside its field's range."""
    if not values:
        return

    rows = db.execute(
        select(
            FieldPlacement.api_name,
            FieldPlacement.label_override,
            FieldDefinition.label,
            FieldDefinition.min_value,
            FieldDefinition.max_value,
        )
        .join(FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id)
        .where(
            FieldPlacement.module_key == module,
            FieldPlacement.status == "active",
            FieldPlacement.api_name.in_(list(values)),
            or_(FieldDefinition.min_value.is_not(None), FieldDefinition.max_value.is_not(None)),
        )
    ).all()

    problems: list[str] = []
    for api_name, label_override, label, low, high in rows:
        value = values.get(api_name)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            # Not a number at all is the schema's refusal to make, not this one.
            continue
        if (low is not None and number < low) or (high is not None and number > high):
            problems.append(f"{label_override or label} must be {_range_text(low, high)}")

    if problems:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "OUT_OF_RANGE", "message": f"{problems[0]}."}
            if len(problems) == 1
            else {"code": "OUT_OF_RANGE", "message": "Some values are out of range:", "details": problems},
        )

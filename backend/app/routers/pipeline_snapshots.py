"""
/api/pipeline-snapshots — the open pipeline as it stood, day by day (migration 0041).

    GET  /api/pipeline-snapshots                anyone with a role
         ?date_from=&date_to=   ?dimension=ALL|BD_OWNER|BOOKING_REGION|SEGMENT
    POST /api/pipeline-snapshots                ADMIN or DEVELOPER
         ?snapshot_date=YYYY-MM-DD   (default: today; a missed month-end
                                      within the grace period is allowed)

Dashboard Phase 1, 28 Sep 2026. The month-end timer writes most of these; the
POST is for a month-end the server missed, and for the first point after a
deployment if the start-up one did not run. What is counted, and why a past
day cannot be rebuilt: app/pipeline_snapshots.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipeline_snapshots as snapshots
from ..auth import require_target_editor
from ..clock import today_company
from ..database import get_db
from ..messages import refusal
from ..models import SNAPSHOT_DIMENSIONS, PipelineSnapshot, User

router = APIRouter(tags=["pipeline snapshots"])


@router.get("/pipeline-snapshots")
def list_snapshots(
    date_from: date | None = None,
    date_to: date | None = None,
    dimension: str | None = None,
    db: Session = Depends(get_db),
):
    if dimension and dimension not in SNAPSHOT_DIMENSIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("SNAPSHOT_DIMENSION_UNKNOWN", "Pick a way to split the pipeline.", list(SNAPSHOT_DIMENSIONS)),
        )
    query = select(PipelineSnapshot)
    if date_from:
        query = query.where(PipelineSnapshot.snapshot_date >= date_from)
    if date_to:
        query = query.where(PipelineSnapshot.snapshot_date <= date_to)
    if dimension:
        query = query.where(PipelineSnapshot.dimension == dimension)
    rows = db.scalars(query.order_by(PipelineSnapshot.snapshot_date, PipelineSnapshot.dimension, PipelineSnapshot.id))
    return [
        {
            "snapshot_date": r.snapshot_date,
            "dimension": r.dimension,
            "bd_owner_id": r.bd_owner_id,
            "booking_region": r.booking_region,
            "segment": r.segment,
            "open_value_usd": float(r.open_value_usd),
            "weighted_value_usd": float(r.weighted_value_usd),
            "deal_count": r.deal_count,
            "unpriced_count": r.unpriced_count,
            "created_at": r.created_at,
            "created_by": r.created_by,
        }
        for r in rows
    ]


@router.post("/pipeline-snapshots")
def take_snapshot(
    snapshot_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_target_editor),
):
    try:
        return snapshots.take(db, snapshot_date or today_company(), actor=user.user_id)
    except snapshots.SnapshotRefused as refused:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if refused.code == "SNAPSHOT_NOT_READY" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, refusal(refused.code, refused.message, refused.details))

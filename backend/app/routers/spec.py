"""
GET /api/spec — the register as last published, for the browser.

The frontend loads this once at start-up and uses it instead of the copy of
spec/fields.json, picklists.json and stages.json built into it (see
frontend/src/lib/spec/source.ts). That is what makes a change published in
Administration reach the live app without a rebuild — decided 21 Sep 2026.
The server's required-field check reads the same version
(app/requirements.py), so what the form marks required and what a save
demands cannot drift apart.

The version number is the ETag: a browser that already holds the latest
version gets a 304 and no body.
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..live_register import published

router = APIRouter(tags=["spec"])


@router.get("/spec")
def get_spec(request: Request, response: Response, db: Session = Depends(get_db)):
    register = published(db)
    if register is None:
        # Never published: the browser keeps the copy it was built with.
        return Response(status_code=204)
    etag = f'"register-{register.version_no}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return {
        "version": register.version_no,
        "fields": register.fields,
        "picklists": register.picklists,
        "stages": register.stages,
    }

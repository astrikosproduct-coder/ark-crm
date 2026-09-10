"""
Sign in with Microsoft Entra.

Authorization code flow with a confidential client: the browser is redirected to
Microsoft, comes back with a code, and THIS SERVER exchanges that code for
tokens using the client secret. The implicit flow is deliberately not used and
its "ID tokens"/"Access tokens" checkboxes should stay unticked on the app
registration.

FIRST SIGN-IN CREATES THE USER, WITH NO ROLES
---------------------------------------------
An employee who has never used the CRM is auto-provisioned here rather than
refused, because refusing would mean an administrator has to pre-create every
person by hand and get their email exactly right. The new row carries ZERO
roles, so it grants nothing — see app/auth.py::require_access. The app
registration is single-tenant, which is what keeps this safe: only accounts in
the organisation's own directory can reach this code at all.
"""

import os
import re

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user, sign_in, sign_out
from ..database import get_db
from ..models import User

router = APIRouter(tags=["auth"])

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")

_USER_ID_PATTERN = re.compile(r"^USR-(\d+)$")

oauth = OAuth()


def _register_entra() -> None:
    """
    Registered lazily so the application still starts — and every route that is
    not sign-in still works — when the Entra variables are absent. During P-1
    setup the credentials arrive after the code does, and a hard failure at
    import time would make that impossible to test.
    """
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        return
    if "entra" in oauth._clients:
        return

    oauth.register(
        name="entra",
        client_id=client_id,
        client_secret=client_secret,
        # Authlib reads the signing keys, issuer and endpoints from here, so the
        # ID token's signature and issuer are validated for us rather than by
        # hand.
        server_metadata_url=(
            f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email User.Read"},
    )


def _entra():
    _register_entra()
    client = oauth.create_client("entra")
    if client is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Microsoft sign-in is not configured on this server "
            "(ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET).",
        )
    return client


def _next_user_id(db: Session) -> str:
    """USR-00N, continuing past the highest that exists."""
    highest = 0
    for existing in db.scalars(select(User.user_id)):
        match = _USER_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"USR-{highest + 1:03d}"


def _resolve_user(db: Session, claims: dict) -> User:
    """
    Find the row this Microsoft identity belongs to, or create one.

    Matching order matters:
      1. entra_object_id — the directory object id, stable across every app
         registration in the tenant. Once linked, this is the only thing that
         identifies a person, so changing an app registration (or an email)
         cannot orphan them.
      2. email, case-insensitively — the FIRST-TIME link only, for a row an
         administrator created ahead of time.
      3. otherwise a new row, with no roles.
    """
    oid = claims.get("oid")
    email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip()
    name = claims.get("name") or email or "Unknown"

    if oid:
        user = db.scalar(select(User).where(User.entra_object_id == oid))
        if user:
            # Keep display data current; Microsoft is the source of truth for it.
            if email:
                user.email = email
            user.name = name
            return user

    if email:
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user:
            user.entra_object_id = oid  # link it, so future sign-ins match on oid
            user.name = name
            return user

    user = User(
        user_id=_next_user_id(db),
        name=name,
        email=email,
        entra_object_id=oid,
        active=True,
    )
    db.add(user)
    db.flush()
    return user


GRAPH_ME = "https://graph.microsoft.com/v1.0/me"

# employeeId is one of the properties Microsoft Graph returns ONLY when it is
# explicitly selected — ask for /me plainly and it is silently absent, which
# reads like a permissions failure and is not one.
GRAPH_SELECT = "id,displayName,mail,userPrincipalName,employeeId,jobTitle,department"


async def _graph_profile(token: dict) -> dict:
    """
    The signed-in user's directory profile, or {} if anything goes wrong.

    BEST EFFORT, ALWAYS. This runs inside the sign-in callback, and enrichment
    must never be able to stop somebody logging in: Graph being slow, the scope
    being missing, the tenant not populating employeeId — every one of those
    returns an empty dict and sign-in carries on. An optional nicety that can
    lock a user out is not a nicety.
    """
    access_token = token.get("access_token")
    if not access_token:
        return {}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                GRAPH_ME,
                params={"$select": GRAPH_SELECT},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code != 200:
            print(f"[auth] Graph profile unavailable ({response.status_code}); continuing without it")
            return {}
        return response.json()
    except Exception as exc:  # noqa: BLE001 — deliberately never fatal
        print(f"[auth] Graph profile lookup failed ({exc!r}); continuing without it")
        return {}


@router.get("/auth/login")
async def login(request: Request):
    """Send the browser to Microsoft. Not an API call — a real navigation."""
    redirect_uri = f"{APP_BASE_URL}/api/auth/callback"
    return await _entra().authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """
    Microsoft sends the browser back here. Exchange the code, resolve the user,
    open the session, and return them to the app.
    """
    try:
        token = await _entra().authorize_access_token(request)
    except OAuthError as exc:
        # Wrong redirect URI, expired code, consent withdrawn. Send them back to
        # a page that can explain rather than rendering a bare JSON error.
        return RedirectResponse(f"{APP_BASE_URL}/signed-out?error={exc.error}")

    claims = token.get("userinfo") or {}
    if not claims.get("oid") and not claims.get("preferred_username"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Microsoft did not return an identifiable user."
        )

    user = _resolve_user(db, claims)

    # Directory attributes, best effort — see _graph_profile. Only ever fills a
    # value in; never clears one the directory happens not to return this time.
    profile = await _graph_profile(token)
    employee_id = (profile.get("employeeId") or "").strip()
    if employee_id:
        user.employee_id = employee_id

    sign_in(request, user, db)
    return RedirectResponse(APP_BASE_URL)


@router.post("/auth/logout")
def logout(request: Request):
    sign_out(request)
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(current_user)):
    """
    Who the frontend thinks it is. Depends on `current_user`, NOT
    `require_access`: a user with no roles must still be able to load this, or
    the app cannot tell them their access is pending.
    """
    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "employee_id": user.employee_id,
        "roles": [r.role_id for r in user.roles],
        "is_admin": any(r.role_id == "ADMIN" for r in user.roles),
        # The frontend switches on this to show the pending-access screen.
        "pending": not user.roles,
    }

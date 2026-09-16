"""
The Astrikos directory, read from Microsoft Graph with the APP's own identity.

WHY APP-ONLY, NOT THE ADMIN'S TOKEN
-----------------------------------
Sign-in asks for delegated `User.Read`, which lets the app read the signed-in
person's own profile and nobody else's. Listing colleagues needs `User.Read.All`.
It is granted as an APPLICATION permission (with admin consent) and used through
the client-credentials flow below, so the server reads the directory without
borrowing, storing or refreshing anybody's sign-in token.

Setup, once, in Entra: App registrations -> ARK CRM -> API permissions ->
Microsoft Graph -> Application permissions -> User.Read.All -> Grant admin
consent for Astrikos. Until that is done Graph answers 403, and this module
turns that into a sentence an administrator can act on.

WHAT IS OFFERED
---------------
Members only, enabled accounts only. Guests (userType 'Guest', the #EXT#
accounts) are left out: they are not Astrikos employees. Microsoft keeps no flag
for service or shared mailboxes, so those still appear if they are ordinary
member accounts; the admin simply does not pick them.

Microsoft says who EXISTS. ARK CRM decides what they may DO — roles are never
read from Entra here.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

GRAPH = "https://graph.microsoft.com/v1.0"
SELECT = "id,displayName,mail,userPrincipalName,employeeId,jobTitle,department,accountEnabled,userType"
MEMBERS_ONLY = "userType eq 'Member' and accountEnabled eq true"
TIMEOUT = 10.0

#: (access_token, expires_at) — the app token lasts about an hour; one per process.
_token_cache: tuple[str, float] | None = None


@dataclass
class DirectoryPerson:
    entra_object_id: str
    name: str
    email: str
    employee_id: str | None
    job_title: str | None
    department: str | None
    is_member: bool
    enabled: bool


def _unavailable(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"code": code, "message": message})


def _app_token() -> str:
    global _token_cache
    if _token_cache and _token_cache[1] - 60 > time.time():
        return _token_cache[0]

    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        raise _unavailable(
            "DIRECTORY_NOT_CONFIGURED",
            "The Microsoft directory is not configured on this server "
            "(ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET).",
        )

    try:
        response = httpx.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise _unavailable("DIRECTORY_UNREACHABLE", f"Could not reach Microsoft: {exc}") from exc
    if response.status_code != 200:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        raise _unavailable(
            "DIRECTORY_TOKEN_REFUSED",
            "Microsoft refused the app's credentials "
            f"({body.get('error', response.status_code)}). Check the client secret has not expired.",
        )

    payload = response.json()
    _token_cache = (payload["access_token"], time.time() + int(payload.get("expires_in", 3600)))
    return _token_cache[0]


def _get(path: str, params: dict[str, str], *, search: bool = False) -> httpx.Response:
    headers = {"Authorization": f"Bearer {_app_token()}"}
    if search:
        # $search, and $filter combined with it, are "advanced queries" and
        # Graph refuses them without this header and $count.
        headers["ConsistencyLevel"] = "eventual"
    try:
        response = httpx.get(f"{GRAPH}{path}", params=params, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise _unavailable("DIRECTORY_UNREACHABLE", f"Could not reach Microsoft Graph: {exc}") from exc

    if response.status_code in (401, 403):
        raise _unavailable(
            "DIRECTORY_PERMISSION_MISSING",
            "ARK CRM is not yet allowed to read the Astrikos directory. In Entra, grant the "
            "app the Microsoft Graph APPLICATION permission User.Read.All and click "
            "'Grant admin consent'. Until then, add people manually.",
        )
    return response


def _person(row: dict) -> DirectoryPerson:
    return DirectoryPerson(
        entra_object_id=row["id"],
        name=row.get("displayName") or row.get("userPrincipalName") or "Unknown",
        email=(row.get("mail") or row.get("userPrincipalName") or "").strip(),
        employee_id=(row.get("employeeId") or "").strip() or None,
        job_title=row.get("jobTitle"),
        department=row.get("department"),
        is_member=row.get("userType") == "Member",
        enabled=bool(row.get("accountEnabled")),
    )


def search_people(text: str, limit: int = 25) -> list[DirectoryPerson]:
    """Members whose name or email starts with a word of `text`."""
    # Graph's $search takes a double-quoted string; neither a quote nor a
    # backslash is ever part of a name worth searching, so they are dropped
    # rather than escaped.
    cleaned = "".join(ch for ch in text if ch not in '"\\').strip()
    if len(cleaned) < 2:
        return []
    response = _get(
        "/users",
        {
            "$search": f'"displayName:{cleaned}" OR "mail:{cleaned}" OR "userPrincipalName:{cleaned}"',
            "$filter": MEMBERS_ONLY,
            "$select": SELECT,
            "$orderby": "displayName",
            "$count": "true",
            "$top": str(limit),
        },
        search=True,
    )
    if response.status_code != 200:
        raise _unavailable(
            "DIRECTORY_ERROR",
            f"Microsoft Graph could not search the directory ({response.status_code}).",
        )
    return [_person(row) for row in response.json().get("value", [])]


def get_person(entra_object_id: str) -> DirectoryPerson | None:
    """One directory entry by object id, or None if there is no such person."""
    response = _get(f"/users/{entra_object_id}", {"$select": SELECT})
    if response.status_code in (400, 404):
        return None
    if response.status_code != 200:
        raise _unavailable(
            "DIRECTORY_ERROR",
            f"Microsoft Graph could not read that person ({response.status_code}).",
        )
    return _person(response.json())

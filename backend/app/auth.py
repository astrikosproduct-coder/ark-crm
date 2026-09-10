"""
Who is making this request.

THE ONE PLACE IDENTITY IS DECIDED
---------------------------------
Every protected route reaches identity through `current_user`, and nothing else
in the application reads the session. That is deliberate: P-1 signs users in
through Microsoft Entra, but the identity SOURCE has already changed once (a
hardcoded USR-001) and will change again (a borrowed app registration is swapped
for the real one on Monday, and a gateway may front this later). Each of those
is a change to this file alone.

AUTHENTICATED IS NOT AUTHORISED
-------------------------------
Every employee in the tenant can authenticate — finance, HR, a new joiner on
their first morning. So a signed-in user with no roles is a real, expected state
and gets NOTHING: `require_access` refuses them, and the frontend shows a
pending-access screen until an administrator grants a role. Defaulting a new
sign-in to any working role, even a read-only one, would put the commercial
pipeline — deal values, margins, TCV — in front of the whole company on day one.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

# The session key holding the signed-in user's id. The session cookie itself is
# signed with SESSION_SECRET by Starlette's SessionMiddleware — see main.py.
SESSION_USER_KEY = "user_id"

ADMIN_ROLE = "ADMIN"


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    The signed-in user, or 401.

    401 rather than a redirect: every caller is either the SPA's axios client,
    which turns 401 into a sign-in redirect of its own, or a script — and a
    script deserves a status code, not an HTML login page.
    """
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not signed in.",
            headers={"WWW-Authenticate": "Session"},
        )

    user = db.get(User, user_id)
    if user is None:
        # The row was deleted while the cookie lived on. Drop the stale session
        # rather than 500-ing on a null user for the rest of its lifetime.
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid.")

    if not user.active:
        # Deactivating a user in Administration must take effect on their next
        # request, not whenever their cookie happens to expire.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated.")

    return user


def require_access(user: User = Depends(current_user)) -> User:
    """
    Signed in AND granted at least one role — the gate on every data route.

    A user with no roles is not an error and not an intruder: they are a real
    employee waiting for an administrator. 403 with a recognisable message, so
    the frontend can tell "you are not signed in" (401 → go sign in) apart from
    "you are signed in but not yet allowed" (403 → pending screen).
    """
    if not user.roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your account has no role yet. An administrator must grant you access.",
        )
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """Administration and the metadata register — ADMIN only."""
    if not any(role.role_id == ADMIN_ROLE for role in user.roles):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Administration is restricted to administrators."
        )
    return user


def sign_in(request: Request, user: User, db: Session) -> None:
    """Attach the session to this user and stamp the sign-in."""
    request.session[SESSION_USER_KEY] = user.user_id
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def sign_out(request: Request) -> None:
    request.session.clear()

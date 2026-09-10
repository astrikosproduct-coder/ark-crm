from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import DirectoryUserOut

router = APIRouter(tags=["directory"])


def _to_directory(user: User) -> DirectoryUserOut:
    """
    Project a User onto the shape the prototype's spec layer already expects.

    Two deliberate concessions to the existing frontend, so that 27 user-lookup
    fields, the filter engine and the list label join all keep working without
    being touched:

    * `id` mirrors `user_id`. src/lib/spec/index.ts idOf() reads `id`, and a
      record without one silently resolves to an empty selection.
    * `roles` is a FLAT list of role keys, not the nested role objects
      /api/admin/users returns. spec/extensions.json filters read
      `roles includes 'BD Owner'`, which evaluates over strings; the comparison
      is slug-normalised, so the BD_OWNER key matches the 'BD Owner' label.

    /api/admin/* keeps the richer nested shape — that is the Administration
    module's own API and its consumer is typed against it.
    """
    return DirectoryUserOut(
        id=user.user_id,
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        active=user.active,
        roles=[role.role_id for role in user.roles],
    )


@router.get("/users", response_model=list[DirectoryUserOut])
def list_users(response: Response, db: Session = Depends(get_db)):
    """
    The user directory, read by every user-lookup field in the application.

    This replaces the former spec/seed/users.json mock collection: users are a
    real database resource and MSW passes /api/users straight through to here.
    Every other collection is still answered by MSW from the store.

    Returns inactive users too. Deactivation must not make an already-assigned
    owner vanish from a record that names them — the filtering of who may be
    PICKED is a spec concern (lookup_filter_expr), not a transport concern.
    """
    users = db.scalars(select(User).order_by(User.name)).all()
    rows = [_to_directory(user) for user in users]
    # Parity with the mock list endpoint, which every list screen reads.
    response.headers["X-Total-Count"] = str(len(rows))
    return rows


@router.get("/users/{user_id}", response_model=DirectoryUserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user {user_id}")
    return _to_directory(user)

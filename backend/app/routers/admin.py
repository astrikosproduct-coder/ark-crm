import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import graph_directory
from ..database import get_db
from ..models import Role, User, UserRole
from ..schemas import (
    ActiveUpdate,
    DirectoryPersonOut,
    NextIdOut,
    RoleAssignment,
    RoleOut,
    UserCreate,
    UserFromDirectory,
    UserOut,
    UserUpdate,
)

router = APIRouter()

USER_ID_PATTERN = re.compile(r"^USR-(\d+)$")


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user {user_id}")
    return user


def _assign_roles(db: Session, user: User, role_ids: list[str]) -> None:
    """
    Replace a user's role set. Unknown role ids are rejected rather than
    silently dropped — a typo in a role key should be visible, not swallowed.
    """
    wanted = list(dict.fromkeys(role_ids))  # de-duplicate, keep order

    if wanted:
        known = set(db.scalars(select(Role.role_id).where(Role.role_id.in_(wanted))))
        unknown = [r for r in wanted if r not in known]
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown role(s): {', '.join(unknown)}",
            )

    db.query(UserRole).filter(UserRole.user_id == user.user_id).delete(
        synchronize_session=False
    )
    for role_id in wanted:
        db.add(UserRole(user_id=user.user_id, role_id=role_id))


# ---------------------------------------------------------------- roles

@router.get("/roles", response_model=list[RoleOut], tags=["roles"])
def list_roles(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """The nine system-defined roles. Seeded, never created through the API."""
    stmt = select(Role).order_by(Role.sort_order)
    if active_only:
        stmt = stmt.where(Role.active.is_(True))
    return db.scalars(stmt).all()


# ---------------------------------------------------------------- users

@router.get("/users/next-id", response_model=NextIdOut, tags=["users"])
def next_user_id(db: Session = Depends(get_db)):
    """
    Suggest the next USR-00N for the Add dialog. A suggestion only — the admin
    types the final value, so this is deliberately not a database sequence.
    """
    return NextIdOut(user_id=_suggested_user_id(db))


def _suggested_user_id(db: Session) -> str:
    highest = 0
    for existing in db.scalars(select(User.user_id)):
        match = USER_ID_PATTERN.match(existing)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"USR-{highest + 1:03d}"


# ---------------------------------------------------------------- directory

def _existing_for(db: Session, oid: str, email: str) -> User | None:
    """The ARK CRM row for a directory person: by directory id, else by email."""
    user = db.scalar(select(User).where(User.entra_object_id == oid))
    if user is None and email:
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    return user


@router.get("/directory/people", response_model=list[DirectoryPersonOut], tags=["directory"])
def search_directory(
    q: str = Query(min_length=2, max_length=100, description="Name or email, at least 2 characters"),
    db: Session = Depends(get_db),
):
    """
    Search the Astrikos Microsoft directory — members with enabled accounts
    only. Needs the Graph application permission User.Read.All; without it the
    answer is a 503 whose message says exactly that.
    """
    out = []
    for person in graph_directory.search_people(q):
        existing = _existing_for(db, person.entra_object_id, person.email)
        out.append(
            DirectoryPersonOut(
                entra_object_id=person.entra_object_id,
                name=person.name,
                email=person.email,
                employee_id=person.employee_id,
                job_title=person.job_title,
                department=person.department,
                user_id=existing.user_id if existing else None,
            )
        )
    return out


@router.post(
    "/users/from-directory",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user_from_directory(payload: UserFromDirectory, db: Session = Depends(get_db)):
    """
    Add a person picked from the directory, with their roles, in one save.

    Name, email and employee id are read from Microsoft HERE, not taken from the
    request, and the row is linked by directory id from the start — so their
    first sign-in matches them on that id and they arrive with the roles already
    granted, instead of on the Access pending screen.
    """
    person = graph_directory.get_person(payload.entra_object_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person is not in the Astrikos directory.")
    if not person.is_member:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{person.name} is a guest account, not an Astrikos employee, and cannot be added.",
        )
    if not person.enabled:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{person.name}'s Microsoft account is disabled, so they could never sign in.",
        )
    if not person.email:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{person.name} has no email address in the directory.",
        )

    existing = _existing_for(db, person.entra_object_id, person.email)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{person.name} is already in ARK CRM as {existing.user_id} — edit that user's roles instead.",
        )

    user_id = (payload.user_id or "").strip() or _suggested_user_id(db)
    if db.get(User, user_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"User id {user_id} is already taken")

    user = User(
        user_id=user_id,
        name=person.name,
        email=person.email,
        entra_object_id=person.entra_object_id,
        employee_id=person.employee_id,
        active=payload.active,
    )
    db.add(user)
    db.flush()  # the FK in user_roles needs the row to exist first

    _assign_roles(db, user, payload.role_ids)

    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(
    q: str | None = Query(default=None, description="Case-insensitive name search"),
    db: Session = Depends(get_db),
):
    """
    Every user with their roles. `q` filters on name, because the Add dialog
    looks a person up by name — nobody remembers a user id.
    """
    stmt = select(User).order_by(User.name)
    if q:
        stmt = stmt.where(User.name.ilike(f"%{q}%"))
    return db.scalars(stmt).all()


@router.get("/users/{user_id}", response_model=UserOut, tags=["users"])
def get_user(user_id: str, db: Session = Depends(get_db)):
    return _get_user_or_404(db, user_id)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.get(User, payload.user_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"User id {payload.user_id} is already taken"
        )

    clash = db.scalar(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.email} already belongs to {clash.user_id}",
        )

    user = User(
        user_id=payload.user_id,
        name=payload.name,
        email=payload.email,
        active=payload.active,
    )
    db.add(user)
    db.flush()  # the FK in user_roles needs the row to exist first

    _assign_roles(db, user, payload.role_ids)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
    changes = payload.model_dump(exclude_unset=True)

    if "email" in changes:
        clash = db.scalar(
            select(User).where(
                func.lower(User.email) == changes["email"].lower(),
                User.user_id != user_id,
            )
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{changes['email']} already belongs to {clash.user_id}",
            )

    for key, value in changes.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut, tags=["users"])
def set_user_active(user_id: str, payload: ActiveUpdate, db: Session = Depends(get_db)):
    """
    Deactivation is not deletion. The user keeps their roles and their history;
    they simply stop being selectable as an owner or approver.
    """
    user = _get_user_or_404(db, user_id)
    user.active = payload.active
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------- user roles

@router.get("/users/{user_id}/roles", response_model=list[RoleOut], tags=["user roles"])
def get_user_roles(user_id: str, db: Session = Depends(get_db)):
    return _get_user_or_404(db, user_id).roles


@router.put("/users/{user_id}/roles", response_model=list[RoleOut], tags=["user roles"])
def replace_user_roles(
    user_id: str, payload: RoleAssignment, db: Session = Depends(get_db)
):
    """
    Replaces the whole set. Sending [] removes every role — that is how the UI
    expresses 'remove this role' without needing a DELETE per assignment.
    """
    user = _get_user_or_404(db, user_id)
    _assign_roles(db, user, payload.role_ids)
    db.commit()
    db.refresh(user)
    return user.roles

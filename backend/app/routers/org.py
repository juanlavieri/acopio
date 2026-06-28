"""Organization management: regions, centers, and the user hierarchy.

All operations are scoped: a manager can only see/manage regions, centers and
users within their slice of the org, and can only assign roles strictly below
their own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth import audit, get_current_user, hash_password, require_country_manager, require_org_manager
from ..db import get_db
from ..models import Center, Region, User
from ..scope import (
    CENTER_MANAGER,
    COUNTRY_MANAGER,
    REGIONAL_MANAGER,
    VOLUNTEER,
    assignable_roles,
    can_manage_user,
    level,
    region_of_user,
    visible_center_ids,
    visible_region_ids,
)

router = APIRouter(prefix="/api/org", tags=["org"])


# --- helpers -------------------------------------------------------------
def _visible_regions(db: Session, user: User) -> list[Region]:
    ids = visible_region_ids(db, user)
    q = db.query(Region)
    if ids is not None:
        if not ids:
            return []
        q = q.filter(Region.id.in_(ids))
    return q.order_by(Region.name).all()


def _visible_centers(db: Session, user: User) -> list[Center]:
    ids = visible_center_ids(db, user)
    q = db.query(Center)
    if ids is not None:
        if not ids:
            return []
        q = q.filter(Center.id.in_(ids))
    return q.order_by(Center.name).all()


def _assert_region_in_scope(db: Session, actor: User, region_id: str) -> Region:
    ids = visible_region_ids(db, actor)
    if ids is not None and region_id not in ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Region outside your scope.")
    region = db.get(Region, region_id)
    if not region:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found.")
    return region


def _assert_center_in_scope(db: Session, actor: User, center_id: str) -> Center:
    ids = visible_center_ids(db, actor)
    if ids is not None and center_id not in ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Center outside your scope.")
    center = db.get(Center, center_id)
    if not center:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Center not found.")
    return center


# --- selectors / overview ------------------------------------------------
@router.get("/centers")
def my_centers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Centers visible to the current user (drives the scope selector)."""
    return {"centers": [c.public() for c in _visible_centers(db, user)]}


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    regions = _visible_regions(db, user)
    centers = _visible_centers(db, user)
    center_ids = visible_center_ids(db, user)

    users_q = db.query(User)
    if center_ids is not None:
        # Show users whose center OR region falls in scope, plus same-region managers.
        region_ids = visible_region_ids(db, user) or set()
        cond_ids = list(center_ids) if center_ids else []
        users = [
            u
            for u in users_q.all()
            if (u.center_id in center_ids if center_ids else False)
            or (u.region_id in region_ids if region_ids else False)
        ]
    else:
        users = users_q.all()

    centers_by_region: dict[str, int] = {}
    for c in db.query(Center).all():
        centers_by_region[c.region_id] = centers_by_region.get(c.region_id, 0) + 1

    return {
        "regions": [r.public(centers=centers_by_region.get(r.id, 0)) for r in regions],
        "centers": [c.public() for c in centers],
        "users": [u.public() for u in users if u.id != user.id] + [user.public()],
        "assignable_roles": assignable_roles(user),
        "can_create_regions": user.role == COUNTRY_MANAGER,
        "can_create_centers": level(user.role) >= level(REGIONAL_MANAGER),
    }


# --- regions -------------------------------------------------------------
class RegionIn(BaseModel):
    name: str
    country: str = "Venezuela"


@router.post("/regions")
def create_region(body: RegionIn, db: Session = Depends(get_db),
                  user: User = Depends(require_country_manager)):
    region = Region(name=body.name.strip(), country=body.country.strip() or "Venezuela", created_by=user.id)
    db.add(region)
    db.commit()
    db.refresh(region)
    audit(db, user, "org.create_region", "region", region.id, {"name": region.name})
    return {"region": region.public(centers=0)}


# --- centers -------------------------------------------------------------
class CenterIn(BaseModel):
    name: str
    region_id: str
    location: str = ""


@router.post("/centers")
def create_center(body: CenterIn, db: Session = Depends(get_db),
                  user: User = Depends(require_org_manager)):
    if level(user.role) < level(REGIONAL_MANAGER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only regional managers and above can create centers.")
    _assert_region_in_scope(db, user, body.region_id)
    center = Center(name=body.name.strip(), region_id=body.region_id, location=body.location.strip(), created_by=user.id)
    db.add(center)
    db.commit()
    db.refresh(center)
    audit(db, user, "org.create_center", "center", center.id, {"name": center.name})
    return {"center": center.public()}


# --- users ---------------------------------------------------------------
class CreateUserIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str
    region_id: str | None = None
    center_id: str | None = None


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    out = [u for u in db.query(User).all() if can_manage_user(db, user, u)]
    return {"users": [u.public() for u in out]}


@router.post("/users")
def create_user(body: CreateUserIn, db: Session = Depends(get_db),
                user: User = Depends(require_org_manager)):
    if body.role not in assignable_roles(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot assign that role.")
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters.")
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    region_id = body.region_id
    center_id = body.center_id

    if body.role == REGIONAL_MANAGER:
        if not region_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Regional managers need a region.")
        _assert_region_in_scope(db, user, region_id)
        center_id = None
    elif body.role in (CENTER_MANAGER, VOLUNTEER):
        if not center_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This role needs a center.")
        center = _assert_center_in_scope(db, user, center_id)
        region_id = center.region_id
    else:  # country_manager — never assignable here (only bootstrap)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid role.")

    new_user = User(
        email=email,
        name=body.name.strip() or email,
        password_hash=hash_password(body.password),
        role=body.role,
        region_id=region_id,
        center_id=center_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    audit(db, user, "org.create_user", "user", new_user.id, {"role": body.role, "email": email})
    return {"user": new_user.public()}


class ActiveIn(BaseModel):
    active: bool


@router.post("/users/{user_id}/active")
def set_active(user_id: str, body: ActiveIn, db: Session = Depends(get_db),
               user: User = Depends(require_org_manager)):
    target = db.get(User, user_id)
    if not target or not can_manage_user(db, user, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot manage this user.")
    target.active = body.active
    db.commit()
    audit(db, user, "org.set_active", "user", target.id, {"active": body.active})
    return {"user": target.public()}


class ReassignIn(BaseModel):
    region_id: str | None = None
    center_id: str | None = None


@router.post("/users/{user_id}/reassign")
def reassign(user_id: str, body: ReassignIn, db: Session = Depends(get_db),
             user: User = Depends(require_org_manager)):
    target = db.get(User, user_id)
    if not target or not can_manage_user(db, user, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot manage this user.")
    if target.role in (CENTER_MANAGER, VOLUNTEER):
        if not body.center_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A center is required.")
        center = _assert_center_in_scope(db, user, body.center_id)
        target.center_id = center.id
        target.region_id = center.region_id
    elif target.role == REGIONAL_MANAGER:
        if not body.region_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A region is required.")
        _assert_region_in_scope(db, user, body.region_id)
        target.region_id = body.region_id
        target.center_id = None
    db.commit()
    audit(db, user, "org.reassign", "user", target.id, {})
    return {"user": target.public()}

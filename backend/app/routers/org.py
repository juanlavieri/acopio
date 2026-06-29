"""Organization & tenant management.

- Super admin: create/list tenants (each tenant = one country manager's org).
- Country manager and below: manage regions, centers and people inside their
  own tenant only. All reads/writes are scoped.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..validators import EmailField

from ..auth import (
    audit,
    get_current_user,
    hash_password,
    require_org_manager,
    require_super_admin,
)
from ..db import get_db
from ..models import Center, Item, Region, Tenant, User
from ..scope import (
    CENTER_MANAGER,
    COUNTRY_MANAGER,
    REGIONAL_MANAGER,
    SUPER_ADMIN,
    VOLUNTEER,
    assignable_roles,
    can_manage_user,
    level,
    tenant_center_ids,
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


# --- selectors -----------------------------------------------------------
@router.get("/centers")
def my_centers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"centers": [c.public() for c in _visible_centers(db, user)]}


# --- super admin: tenants -----------------------------------------------
class TenantIn(BaseModel):
    org_name: str
    country: str
    manager_name: str
    manager_email: EmailField
    manager_password: str


@router.get("/tenants")
def list_tenants(db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    out = []
    for tnt in db.query(Tenant).order_by(Tenant.created_at.desc()).all():
        managers = db.query(User).filter(User.tenant_id == tnt.id, User.role == COUNTRY_MANAGER).all()
        center_ids = tenant_center_ids(db, tnt.id)
        users = db.query(User).filter(User.tenant_id == tnt.id).count()
        items = db.query(Item).filter(Item.center_id.in_(center_ids)).count() if center_ids else 0
        out.append(tnt.public(extra={
            "managers": [{"id": m.id, "name": m.name, "email": m.email, "active": m.active} for m in managers],
            "centers": len(center_ids), "users": users, "items": items,
        }))
    return {"tenants": out}


def _ai_status(db: Session, user: User) -> dict:
    from ..config import settings
    from ..services.llm import resolve_tenant_key

    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id else None
    enabled = bool(resolve_tenant_key(db, user))
    if tenant and tenant.openai_api_key:
        source = "own"
    elif enabled:
        source = "platform"
    else:
        source = "disabled"
    return {
        "ai_enabled": enabled,
        "source": source,
        "has_own_key": bool(tenant and tenant.openai_api_key),
        "use_platform_key": bool(tenant and tenant.use_platform_key),
        "platform_key_available": bool(settings.openai_api_key),
    }


@router.get("/ai-settings")
def ai_settings(db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    return _ai_status(db, user)


class AiKeyIn(BaseModel):
    api_key: str = ""


@router.post("/ai-key")
def set_ai_key(body: AiKeyIn, db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    if user.role != COUNTRY_MANAGER or not user.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the organization's country manager can set the AI key.")
    tenant = db.get(Tenant, user.tenant_id)
    key = (body.api_key or "").strip()
    tenant.openai_api_key = key or None
    db.commit()
    audit(db, user, "org.set_ai_key", "tenant", tenant.id, {"has_own_key": bool(key)})
    return _ai_status(db, user)


class PlatformKeyIn(BaseModel):
    enabled: bool


@router.post("/tenants/{tenant_id}/platform-key")
def set_platform_key(tenant_id: str, body: PlatformKeyIn, db: Session = Depends(get_db),
                     admin: User = Depends(require_super_admin)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")
    tenant.use_platform_key = bool(body.enabled)
    db.commit()
    audit(db, admin, "org.platform_key", "tenant", tenant.id, {"enabled": tenant.use_platform_key})
    return {"tenant": tenant.public()}


@router.post("/tenants")
def create_tenant(body: TenantIn, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    if len(body.manager_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters.")
    email = body.manager_email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    tenant = Tenant(name=body.org_name.strip(), country=body.country.strip(), created_by=admin.id)
    db.add(tenant)
    db.flush()
    region = Region(name=body.country.strip() or body.org_name.strip(), country=body.country.strip(), tenant_id=tenant.id, created_by=admin.id)
    db.add(region)
    db.flush()
    db.add(Center(name="Centro Principal", region_id=region.id, location=body.country.strip(), created_by=admin.id))
    manager = User(
        email=email, name=body.manager_name.strip() or email,
        password_hash=hash_password(body.manager_password), role=COUNTRY_MANAGER, tenant_id=tenant.id,
    )
    db.add(manager)
    db.commit()
    db.refresh(tenant)
    db.refresh(manager)
    audit(db, admin, "org.create_tenant", "tenant", tenant.id, {"country": tenant.country, "manager": email})
    return {"tenant": tenant.public(), "manager": manager.public()}


# --- overview (managers within a tenant) --------------------------------
@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    regions = _visible_regions(db, user)
    centers = _visible_centers(db, user)
    people = [u for u in db.query(User).all() if can_manage_user(db, user, u)]
    centers_by_region: dict[str, int] = {}
    for c in db.query(Center).all():
        centers_by_region[c.region_id] = centers_by_region.get(c.region_id, 0) + 1
    return {
        "regions": [r.public(centers=centers_by_region.get(r.id, 0)) for r in regions],
        "centers": [c.public() for c in centers],
        "users": [u.public() for u in people] + [user.public()],
        "assignable_roles": assignable_roles(user),
        "can_create_regions": level(user.role) >= level(COUNTRY_MANAGER),
        "can_create_centers": level(user.role) >= level(REGIONAL_MANAGER),
        "is_country_manager": user.role == COUNTRY_MANAGER,
        "ai": _ai_status(db, user),
    }


# --- regions -------------------------------------------------------------
class RegionIn(BaseModel):
    name: str
    country: str = ""


@router.post("/regions")
def create_region(body: RegionIn, db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    if user.role != COUNTRY_MANAGER or not user.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a country manager can create regions in their organization.")
    tenant = db.get(Tenant, user.tenant_id)
    region = Region(name=body.name.strip(), country=(body.country.strip() or (tenant.country if tenant else "")),
                    tenant_id=user.tenant_id, created_by=user.id)
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
def create_center(body: CenterIn, db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    if level(user.role) < level(REGIONAL_MANAGER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only regional managers and above can create centers.")
    _assert_region_in_scope(db, user, body.region_id)
    center = Center(name=body.name.strip(), region_id=body.region_id, location=body.location.strip(), created_by=user.id)
    db.add(center)
    db.commit()
    db.refresh(center)
    audit(db, user, "org.create_center", "center", center.id, {"name": center.name})
    return {"center": center.public()}


# --- users (within a tenant) --------------------------------------------
class CreateUserIn(BaseModel):
    email: EmailField
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
def create_user(body: CreateUserIn, db: Session = Depends(get_db), user: User = Depends(require_org_manager)):
    if not user.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Use tenant management to create country managers.")
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
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid role.")

    new_user = User(
        email=email, name=body.name.strip() or email, password_hash=hash_password(body.password),
        role=body.role, tenant_id=user.tenant_id, region_id=region_id, center_id=center_id,
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

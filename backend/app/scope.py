"""Role hierarchy + multi-tenant scoping.

Hierarchy (high → low):
    super_admin      → manages ALL tenants (organizations)
    country_manager  → owns ONE tenant; manages everything inside it
    regional_manager → manages centers + people in their region
    center_manager   → manages volunteers in their center
    volunteer        → records stock at their center

Each tenant (organization) is isolated: a country manager and everyone below
them only see their own tenant's regions, centers, people and inventory. The
super admin sees everything and provisions country managers.
"""
from __future__ import annotations

from sqlalchemy import false
from sqlalchemy.orm import Session

from .models import Center, Region, User

SUPER_ADMIN = "super_admin"
COUNTRY_MANAGER = "country_manager"
REGIONAL_MANAGER = "regional_manager"
CENTER_MANAGER = "center_manager"
VOLUNTEER = "volunteer"

ROLE_LEVEL = {VOLUNTEER: 0, CENTER_MANAGER: 1, REGIONAL_MANAGER: 2, COUNTRY_MANAGER: 3, SUPER_ADMIN: 4}
ROLES = [SUPER_ADMIN, COUNTRY_MANAGER, REGIONAL_MANAGER, CENTER_MANAGER, VOLUNTEER]


def level(role: str) -> int:
    return ROLE_LEVEL.get(role, 0)


def tenant_center_ids(db: Session, tenant_id: str | None) -> set[str]:
    if not tenant_id:
        return set()
    region_ids = [r.id for r in db.query(Region.id).filter(Region.tenant_id == tenant_id).all()]
    if not region_ids:
        return set()
    return {c.id for c in db.query(Center.id).filter(Center.region_id.in_(region_ids)).all()}


def region_of_user(db: Session, user: User) -> str | None:
    if user.region_id:
        return user.region_id
    if user.center_id:
        c = db.get(Center, user.center_id)
        return c.region_id if c else None
    return None


def visible_center_ids(db: Session, user: User) -> set[str] | None:
    """Center ids the user can see. None == all centers (super admin only)."""
    if user.role == SUPER_ADMIN:
        return None
    if user.role == COUNTRY_MANAGER:
        return tenant_center_ids(db, user.tenant_id)
    if user.role == REGIONAL_MANAGER:
        if not user.region_id:
            return set()
        return {c.id for c in db.query(Center).filter(Center.region_id == user.region_id).all()}
    return {user.center_id} if user.center_id else set()


def visible_region_ids(db: Session, user: User) -> set[str] | None:
    if user.role == SUPER_ADMIN:
        return None
    if user.role == COUNTRY_MANAGER:
        if not user.tenant_id:
            return set()
        return {r.id for r in db.query(Region.id).filter(Region.tenant_id == user.tenant_id).all()}
    if user.role == REGIONAL_MANAGER:
        return {user.region_id} if user.region_id else set()
    r = region_of_user(db, user)
    return {r} if r else set()


def scope_query_by_center(query, model, center_ids: set[str] | None):
    """Filter a query of a model that has ``center_id`` by visible centers."""
    if center_ids is None:
        return query
    if not center_ids:
        return query.filter(false())
    return query.filter(model.center_id.in_(center_ids))


def user_in_scope(db: Session, actor: User, target: User) -> bool:
    if actor.role == SUPER_ADMIN:
        return True
    if actor.role == COUNTRY_MANAGER:
        return bool(actor.tenant_id) and target.tenant_id == actor.tenant_id
    if actor.role == REGIONAL_MANAGER:
        return bool(actor.region_id) and region_of_user(db, target) == actor.region_id
    if actor.role == CENTER_MANAGER:
        return bool(actor.center_id) and target.center_id == actor.center_id
    return False


def can_manage_user(db: Session, actor: User, target: User) -> bool:
    if target.id == actor.id:
        return False
    if level(actor.role) <= level(target.role):
        return False
    return user_in_scope(db, actor, target)


def assignable_roles(actor: User) -> list[str]:
    """Roles an actor may assign. Country managers are created by the super
    admin through the tenant flow, so they are not offered here for others."""
    return [r for r in ROLES if level(r) < level(actor.role) and r != SUPER_ADMIN]


def can_manage_org(user: User) -> bool:
    return level(user.role) >= ROLE_LEVEL[CENTER_MANAGER]


def resolve_target_center(db: Session, user: User, center_id_param: str | None) -> str:
    """Pick the center an action applies to, enforcing scope."""
    if user.center_id:
        return user.center_id
    vis = visible_center_ids(db, user)
    if not center_id_param:
        raise ValueError("A center must be selected for this action.")
    if vis is not None and center_id_param not in vis:
        raise ValueError("That center is outside your scope.")
    if not db.get(Center, center_id_param):
        raise ValueError("Center not found.")
    return center_id_param

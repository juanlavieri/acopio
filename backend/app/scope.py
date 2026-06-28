"""Role hierarchy + scoping rules.

Hierarchy (high → low):
    country_manager  → manages everything
    regional_manager → manages centers + people in their region
    center_manager   → manages volunteers in their center
    volunteer        → records stock at their center

A user can manage any user/role strictly below them, within their scope.
Inventory is tracked per collection center; a viewer sees only the centers in
their scope (a country manager sees them all).
"""
from __future__ import annotations

from sqlalchemy import false
from sqlalchemy.orm import Session

from .models import Center, User

COUNTRY_MANAGER = "country_manager"
REGIONAL_MANAGER = "regional_manager"
CENTER_MANAGER = "center_manager"
VOLUNTEER = "volunteer"

ROLE_LEVEL = {VOLUNTEER: 0, CENTER_MANAGER: 1, REGIONAL_MANAGER: 2, COUNTRY_MANAGER: 3}
ROLES = [COUNTRY_MANAGER, REGIONAL_MANAGER, CENTER_MANAGER, VOLUNTEER]


def level(role: str) -> int:
    return ROLE_LEVEL.get(role, 0)


def region_of_user(db: Session, user: User) -> str | None:
    if user.region_id:
        return user.region_id
    if user.center_id:
        c = db.get(Center, user.center_id)
        return c.region_id if c else None
    return None


def visible_center_ids(db: Session, user: User) -> set[str] | None:
    """Center ids the user can see. None == all centers (country manager)."""
    if user.role == COUNTRY_MANAGER:
        return None
    if user.role == REGIONAL_MANAGER:
        if not user.region_id:
            return set()
        return {c.id for c in db.query(Center).filter(Center.region_id == user.region_id).all()}
    return {user.center_id} if user.center_id else set()


def visible_region_ids(db: Session, user: User) -> set[str] | None:
    if user.role == COUNTRY_MANAGER:
        return None
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
    if actor.role == COUNTRY_MANAGER:
        return True
    if actor.role == REGIONAL_MANAGER:
        return region_of_user(db, target) == actor.region_id and actor.region_id is not None
    if actor.role == CENTER_MANAGER:
        return target.center_id == actor.center_id and actor.center_id is not None
    return False


def can_manage_user(db: Session, actor: User, target: User) -> bool:
    if target.id == actor.id:
        return False
    if level(actor.role) <= level(target.role):
        return False
    return user_in_scope(db, actor, target)


def assignable_roles(actor: User) -> list[str]:
    """Roles an actor is allowed to assign (strictly below their own)."""
    return [r for r in ROLES if level(r) < level(actor.role)]


def can_manage_org(user: User) -> bool:
    """Whether the user can manage any people/regions/centers."""
    return level(user.role) >= ROLE_LEVEL[CENTER_MANAGER]


def resolve_target_center(db: Session, user: User, center_id_param: str | None) -> str:
    """Pick the center an action applies to, enforcing scope.

    Center-scoped users (volunteer / center_manager) always act on their own
    center. Higher managers must specify a center within their scope.
    """
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

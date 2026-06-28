"""Field requests / requisitions: the demand side of a collection center.

Centers and the field log what they NEED; managers fulfil those needs from
stock (which records a real dispatch movement, FEFO-aware), so supply meets
demand with full traceability and priority/SLA visibility.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import audit, get_current_user
from ..db import get_db
from ..models import Item, Need, User
from ..scope import resolve_target_center, scope_query_by_center, visible_center_ids
from ..services.inventory import record_movement

router = APIRouter(prefix="/api/needs", tags=["needs"])

PRIORITIES = {"low", "normal", "high", "urgent"}


class NeedIn(BaseModel):
    item_name: str
    category_kind: str = "other"
    quantity: float
    unit: str = "unit"
    priority: str = "normal"
    needed_by: date | None = None
    note: str = ""
    center_id: str | None = None


@router.get("")
def list_needs(
    status_filter: str | None = Query(default=None, alias="status"),
    center_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    if center_id and vis is not None and center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That center is outside your scope.")
    q = scope_query_by_center(db.query(Need), Need, vis)
    if center_id:
        q = q.filter(Need.center_id == center_id)
    if status_filter:
        q = q.filter(Need.status == status_filter)
    # Priority ordering: urgent first, then by needed_by/created.
    order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    needs = sorted(
        q.order_by(Need.created_at.desc()).limit(300).all(),
        key=lambda n: (n.status in ("fulfilled", "cancelled"), order.get(n.priority, 2), n.created_at and -n.created_at.timestamp()),
    )
    return {"needs": [n.public() for n in needs]}


@router.post("")
def create_need(body: NeedIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        center_id = resolve_target_center(db, user, body.center_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    priority = body.priority if body.priority in PRIORITIES else "normal"
    need = Need(
        center_id=center_id,
        item_name=body.item_name.strip(),
        category_kind=body.category_kind or "other",
        quantity=abs(float(body.quantity)),
        unit=body.unit or "unit",
        priority=priority,
        needed_by=body.needed_by,
        note=body.note or "",
        requested_by=user.id,
    )
    db.add(need)
    db.commit()
    db.refresh(need)
    audit(db, user, "need.create", "need", need.id, {"item": need.item_name, "qty": need.quantity, "priority": priority})
    return {"need": need.public()}


class NeedUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None


@router.patch("/{need_id}")
def update_need(need_id: str, body: NeedUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    need = _scoped_need(db, user, need_id)
    if body.status in {"open", "partial", "fulfilled", "cancelled"}:
        need.status = body.status
    if body.priority in PRIORITIES:
        need.priority = body.priority
    db.commit()
    audit(db, user, "need.update", "need", need.id, {"status": need.status})
    return {"need": need.public()}


class FulfillIn(BaseModel):
    quantity: float | None = None


@router.post("/{need_id}/fulfill")
def fulfill_need(need_id: str, body: FulfillIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Dispatch stock to satisfy (part of) a need. Records a real OUT movement."""
    need = _scoped_need(db, user, need_id)
    remaining_need = max(need.quantity - (need.fulfilled_quantity or 0.0), 0.0)
    want = float(body.quantity) if body.quantity else remaining_need
    want = min(want, remaining_need) if remaining_need > 0 else want
    if want <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing left to fulfill.")

    # Find a matching in-stock item in the same center.
    like = f"%{need.item_name.lower()}%"
    item = (
        db.query(Item)
        .filter(Item.center_id == need.center_id, or_(Item.canonical_name.ilike(like), Item.barcode == need.item_name))
        .order_by(Item.quantity.desc())
        .first()
    )
    if not item or (item.quantity or 0.0) <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "No matching stock available to fulfill this need.")

    dispatch = min(want, item.quantity)
    record_movement(
        db, item=item, type="out", quantity=dispatch, user=user, unit=item.unit,
        party=need.note or "Field request", reason="distributed",
        note=f"Fulfilling request {need.id}", source="manual",
    )
    need.fulfilled_quantity = round((need.fulfilled_quantity or 0.0) + dispatch, 4)
    need.status = "fulfilled" if need.fulfilled_quantity >= need.quantity else "partial"
    db.commit()
    audit(db, user, "need.fulfill", "need", need.id, {"dispatched": dispatch, "item": item.canonical_name})
    return {"need": need.public(), "dispatched": dispatch, "item": item.public()}


def _scoped_need(db: Session, user: User, need_id: str) -> Need:
    need = db.get(Need, need_id)
    if not need:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found.")
    vis = visible_center_ids(db, user)
    if vis is not None and need.center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That need is outside your scope.")
    return need

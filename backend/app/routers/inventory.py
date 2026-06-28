"""Inventory: items, movements, categories, flexible schema, audit log.

Everything is scoped to the centers the current user can see.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import audit, get_current_user
from ..db import get_db
from ..models import (
    AuditLog,
    Batch,
    Category,
    CustomField,
    CustomRecord,
    CustomTable,
    Item,
    Movement,
    User,
)
from ..scope import resolve_target_center, scope_query_by_center, visible_center_ids
from ..services.expiry import expiry_status, item_expiry_info, today
from ..services.inventory import correct_stock, record_movement, resolve_or_create_item, void_movement
from ..services.semantic import get_index


def _enrich(db: Session, items: list[Item]) -> list[dict]:
    out = []
    for it in items:
        d = it.public()
        d.update(item_expiry_info(db, it.id))
        out.append(d)
    return out

router = APIRouter(prefix="/api", tags=["inventory"])


def _scoped_center(center_id: str | None, vis: set[str] | None) -> str | None:
    """Validate an explicit center filter against the viewer's scope."""
    if center_id and vis is not None and center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That center is outside your scope.")
    return center_id


# --- items ---------------------------------------------------------------
@router.get("/items")
def list_items(
    q: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    center_id: str | None = Query(default=None),
    semantic: bool = Query(default=False),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    center_id = _scoped_center(center_id, vis)

    if q and semantic:
        hits = get_index().search(q, limit * 2)
        items = []
        for iid, _ in hits:
            it = db.get(Item, iid)
            if not it:
                continue
            if vis is not None and it.center_id not in vis:
                continue
            if center_id and it.center_id != center_id:
                continue
            items.append(it)
            if len(items) >= limit:
                break
        return {"items": _enrich(db, items)}

    query = db.query(Item)
    query = scope_query_by_center(query, Item, vis)
    if center_id:
        query = query.filter(Item.center_id == center_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(Item.canonical_name.ilike(like), Item.description.ilike(like), Item.barcode.ilike(like))
        )
    if category_id:
        query = query.filter(Item.category_id == category_id)
    items = query.order_by(Item.canonical_name).limit(limit).all()
    return {"items": _enrich(db, items)}


def _require_item_in_scope(db: Session, user: User, item_id: str) -> Item:
    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    vis = visible_center_ids(db, user)
    if vis is not None and it.center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Item outside your scope.")
    return it


@router.get("/items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    it = _require_item_in_scope(db, user, item_id)
    movements = (
        db.query(Movement).filter(Movement.item_id == item_id)
        .order_by(Movement.created_at.desc()).limit(50).all()
    )
    batches = (
        db.query(Batch).filter(Batch.item_id == item_id, Batch.qty_remaining > 0)
        .order_by(Batch.expiry_date.is_(None), Batch.expiry_date.asc()).all()
    )
    item_dict = it.public()
    item_dict.update(item_expiry_info(db, it.id))
    batch_dicts = [{**b.public(), "expiry_status": expiry_status(b.expiry_date)} for b in batches]
    return {"item": item_dict, "movements": [m.public() for m in movements], "batches": batch_dicts}


class ItemIn(BaseModel):
    name: str
    unit: str = "unit"
    description: str = ""
    category_id: str | None = None
    center_id: str | None = None
    min_quantity: float = 0.0
    barcode: str = ""
    attributes: dict = {}


@router.post("/items")
def create_item(body: ItemIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        center_id = resolve_target_center(db, user, body.center_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    category = db.get(Category, body.category_id) if body.category_id else None
    item, created = resolve_or_create_item(
        db, name=body.name, user=user, center_id=center_id, unit=body.unit,
        description=body.description, attributes=body.attributes, category=category,
    )
    if body.min_quantity:
        item.min_quantity = body.min_quantity
    if body.barcode:
        item.barcode = body.barcode
    db.commit()
    audit(db, user, "item.create" if created else "item.match", "item", item.id,
          {"name": item.canonical_name, "center_id": center_id})
    return {"item": item.public(), "created": created}


class ItemUpdate(BaseModel):
    canonical_name: str | None = None
    description: str | None = None
    unit: str | None = None
    category_id: str | None = None
    min_quantity: float | None = None
    barcode: str | None = None
    attributes: dict | None = None


@router.patch("/items/{item_id}")
def update_item(item_id: str, body: ItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    it = _require_item_in_scope(db, user, item_id)
    if body.canonical_name is not None:
        it.canonical_name = body.canonical_name
    if body.description is not None:
        it.description = body.description
    if body.unit is not None:
        it.unit = body.unit
    if body.category_id is not None:
        it.category_id = body.category_id or None
    if body.min_quantity is not None:
        it.min_quantity = body.min_quantity
    if body.barcode is not None:
        it.barcode = body.barcode
    if body.attributes is not None:
        it.attributes = {**(it.attributes or {}), **body.attributes}
    db.commit()
    get_index().upsert(it.id, f"{it.canonical_name}. {it.description}")
    audit(db, user, "item.update", "item", it.id, {})
    return {"item": it.public()}


@router.delete("/items/{item_id}")
def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    it = _require_item_in_scope(db, user, item_id)
    db.query(Movement).filter(Movement.item_id == item_id).delete()
    db.delete(it)
    db.commit()
    get_index().remove(item_id)
    audit(db, user, "item.delete", "item", item_id, {})
    return {"ok": True}


# --- movements -----------------------------------------------------------
class MovementIn(BaseModel):
    item_id: str | None = None
    item_name: str | None = None
    type: str = "in"
    quantity: float
    unit: str | None = None
    party: str = ""
    location: str = ""
    note: str = ""
    reason: str = ""
    expiry_date: date | None = None
    lot_code: str = ""
    center_id: str | None = None


@router.post("/movements")
def create_movement(body: MovementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.item_id:
        item = _require_item_in_scope(db, user, body.item_id)
    elif body.item_name:
        try:
            center_id = resolve_target_center(db, user, body.center_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        item, _ = resolve_or_create_item(db, name=body.item_name, user=user, center_id=center_id, unit=body.unit or "unit")
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide item_id or item_name.")

    mv = record_movement(
        db, item=item, type=body.type, quantity=body.quantity, user=user,
        unit=body.unit, party=body.party, location=body.location, note=body.note,
        reason=body.reason, expiry_date=body.expiry_date, lot_code=body.lot_code, source="manual",
    )
    return {"movement": mv.public(), "item": item.public()}


class CorrectIn(BaseModel):
    quantity: float
    note: str = ""


@router.post("/items/{item_id}/correct")
def correct_item(item_id: str, body: CorrectIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Set an item's stock to the correct value (logged as a correction)."""
    item = _require_item_in_scope(db, user, item_id)
    mv = correct_stock(db, item=item, target=body.quantity, user=user, note=body.note, source="manual")
    return {"item": item.public(), "corrected": mv is not None}


@router.post("/movements/{movement_id}/void")
def void_movement_route(movement_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Undo a wrong movement with a compensating reversal."""
    mv = db.get(Movement, movement_id)
    if not mv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movement not found.")
    vis = visible_center_ids(db, user)
    if vis is not None and mv.center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your scope.")
    if mv.voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry was already undone.")
    reversal = void_movement(db, movement=mv, user=user, source="manual")
    item = db.get(Item, mv.item_id)
    return {"ok": True, "reversed": reversal is not None, "item": item.public() if item else None}


@router.get("/movements")
def list_movements(
    item_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    center_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    center_id = _scoped_center(center_id, vis)
    query = scope_query_by_center(db.query(Movement), Movement, vis)
    if item_id:
        query = query.filter(Movement.item_id == item_id)
    if type:
        query = query.filter(Movement.type == type)
    if center_id:
        query = query.filter(Movement.center_id == center_id)
    movements = query.order_by(Movement.created_at.desc()).limit(limit).all()
    return {"movements": [m.public() for m in movements]}


# --- alerts (expiry + low stock) ----------------------------------------
def _scoped_batches(db: Session, vis: set[str] | None, center_id: str | None):
    q = db.query(Batch).filter(Batch.qty_remaining > 0)
    if vis is not None:
        q = scope_query_by_center(q, Batch, vis)
    if center_id:
        q = q.filter(Batch.center_id == center_id)
    return q


@router.get("/alerts")
def alerts(
    days: int = Query(default=30, le=365),
    center_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    center_id = _scoped_center(center_id, vis)
    ref = today()

    batches = _scoped_batches(db, vis, center_id).filter(Batch.expiry_date.isnot(None)).all()
    expired, expiring = [], []
    for b in batches:
        delta = (b.expiry_date - ref).days
        rec = {**b.public(), "days": delta, "expiry_status": expiry_status(b.expiry_date)}
        if delta < 0:
            expired.append(rec)
        elif delta <= days:
            expiring.append(rec)
    expired.sort(key=lambda x: x["expiry_date"])
    expiring.sort(key=lambda x: x["expiry_date"])

    iq = scope_query_by_center(db.query(Item), Item, vis)
    if center_id:
        iq = iq.filter(Item.center_id == center_id)
    low = [
        it.public()
        for it in iq.all()
        if (it.quantity or 0.0) <= (it.min_quantity if it.min_quantity else 5)
    ]
    low.sort(key=lambda x: x["quantity"])

    return {"expired": expired, "expiring": expiring, "low_stock": low, "days": days}


@router.get("/expiring")
def expiring(
    days: int = Query(default=90, le=730),
    center_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    center_id = _scoped_center(center_id, vis)
    ref = today()
    out = []
    for b in _scoped_batches(db, vis, center_id).filter(Batch.expiry_date.isnot(None)).all():
        delta = (b.expiry_date - ref).days
        if delta <= days:
            out.append({**b.public(), "days": delta, "expiry_status": expiry_status(b.expiry_date)})
    out.sort(key=lambda x: x["expiry_date"])
    return {"batches": out}


# --- categories ----------------------------------------------------------
@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return {"categories": [c.public() for c in db.query(Category).order_by(Category.name).all()]}


# --- flexible schema -----------------------------------------------------
@router.get("/schema/fields")
def list_fields(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return {"fields": [f.public() for f in db.query(CustomField).all()]}


@router.get("/schema/tables")
def list_tables(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    tables = db.query(CustomTable).all()
    out = []
    for t in tables:
        records = db.query(CustomRecord).filter(CustomRecord.table_id == t.id).count()
        out.append({**t.public(), "record_count": records})
    return {"tables": out}


@router.get("/schema/tables/{name}/records")
def list_records(name: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    t = db.query(CustomTable).filter(CustomTable.name == name).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found.")
    recs = db.query(CustomRecord).filter(CustomRecord.table_id == t.id).order_by(CustomRecord.created_at.desc()).all()
    return {"table": t.public(), "records": [r.public() for r in recs]}


# --- corrections log -----------------------------------------------------
@router.get("/corrections")
def list_corrections(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    q = scope_query_by_center(db.query(Movement), Movement, vis).filter(Movement.reason == "correction")
    rows = q.order_by(Movement.created_at.desc()).limit(limit).all()
    return {"corrections": [m.public() for m in rows]}


# --- audit log -----------------------------------------------------------
@router.get("/audit")
def list_audit(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit * 3).all()
    if vis is not None:
        # Keep logs from users within scope (by their center) or yourself.
        allowed_user_ids = {
            u.id for u in db.query(User).all() if (u.center_id in vis) or u.id == user.id
        }
        logs = [a for a in logs if a.user_id in allowed_user_ids][:limit]
    else:
        logs = logs[:limit]
    return {"logs": [a.public() for a in logs]}

"""CSV exports for donor / coordination reporting (scoped to the viewer)."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Batch, Item, Movement, User
from ..scope import scope_query_by_center, visible_center_ids
from ..services.expiry import expiry_status, item_expiry_info, today

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(rows: list[list], header: list[str], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/items.csv")
def export_items(center_id: str | None = Query(default=None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    vis = visible_center_ids(db, user)
    q = scope_query_by_center(db.query(Item), Item, vis)
    if center_id:
        q = q.filter(Item.center_id == center_id)
    rows = []
    for it in q.order_by(Item.canonical_name).all():
        info = item_expiry_info(db, it.id)
        rows.append([
            it.canonical_name, it.category.name if it.category else "", it.center.name if it.center else "",
            it.unit, it.quantity, it.min_quantity or 0, it.barcode or "",
            info["earliest_expiry"] or "", info["expiry_status"],
        ])
    header = ["item", "category", "center", "unit", "quantity", "min_quantity", "barcode",
              "earliest_expiry", "expiry_status"]
    return _csv_response(rows, header, "acopio_inventory.csv")


@router.get("/movements.csv")
def export_movements(center_id: str | None = Query(default=None), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    vis = visible_center_ids(db, user)
    q = scope_query_by_center(db.query(Movement), Movement, vis)
    if center_id:
        q = q.filter(Movement.center_id == center_id)
    rows = []
    for m in q.order_by(Movement.created_at.desc()).limit(10000).all():
        rows.append([
            m.created_at.isoformat() if m.created_at else "", m.type, m.item.canonical_name if m.item else "",
            m.quantity, m.unit, m.party, m.reason, m.note,
            m.user.name if m.user else "", m.balance_after,
            m.expiry_date.isoformat() if m.expiry_date else "", m.lot_code or "",
        ])
    header = ["date", "type", "item", "quantity", "unit", "party", "reason", "note", "by", "balance_after",
              "expiry_date", "lot"]
    return _csv_response(rows, header, "acopio_movements.csv")


@router.get("/expiring.csv")
def export_expiring(days: int = Query(default=180, le=730), center_id: str | None = Query(default=None),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vis = visible_center_ids(db, user)
    q = db.query(Batch).filter(Batch.qty_remaining > 0, Batch.expiry_date.isnot(None))
    q = scope_query_by_center(q, Batch, vis)
    if center_id:
        q = q.filter(Batch.center_id == center_id)
    ref = today()
    rows = []
    for b in q.order_by(Batch.expiry_date.asc()).all():
        delta = (b.expiry_date - ref).days
        if delta <= days:
            rows.append([
                b.item.canonical_name if b.item else "", b.center_id or "", b.lot_code or "",
                b.expiry_date.isoformat(), delta, b.qty_remaining, expiry_status(b.expiry_date),
            ])
    header = ["item", "center_id", "lot", "expiry_date", "days_to_expiry", "qty_remaining", "status"]
    return _csv_response(rows, header, "acopio_expiring.csv")

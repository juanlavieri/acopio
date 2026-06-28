"""Expiry, batch/lot and FEFO (First-Expired-First-Out) helpers.

Thresholds follow the Logistics Cluster / humanitarian guidance:
  expired  : past expiry — must be segregated and not distributed
  critical : <= 30 days  (0-1 month — urgent)
  warning  : <= 90 days  (1-3 months — notify program staff)
  caution  : <= 180 days (under the usual 6-month acceptance window)
  ok       : > 180 days
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import Batch, Item, User

CRITICAL_DAYS = 30
WARNING_DAYS = 90
CAUTION_DAYS = 180


def today() -> date:
    return datetime.now(timezone.utc).date()


def expiry_status(expiry: date | None, ref: date | None = None) -> str:
    if not expiry:
        return "none"
    ref = ref or today()
    days = (expiry - ref).days
    if days < 0:
        return "expired"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= WARNING_DAYS:
        return "warning"
    if days <= CAUTION_DAYS:
        return "caution"
    return "ok"


def item_expiry_info(db: Session, item_id: str) -> dict:
    batches = (
        db.query(Batch)
        .filter(Batch.item_id == item_id, Batch.qty_remaining > 0, Batch.expiry_date.isnot(None))
        .all()
    )
    if not batches:
        return {"earliest_expiry": None, "expiry_status": "none"}
    earliest = min(b.expiry_date for b in batches)
    return {"earliest_expiry": earliest.isoformat(), "expiry_status": expiry_status(earliest)}


def create_batch(db: Session, *, item: Item, qty: float, expiry: date | None,
                 lot: str, party: str, user: User | None) -> Batch:
    batch = Batch(
        item_id=item.id,
        center_id=item.center_id,
        lot_code=lot or "",
        expiry_date=expiry,
        qty_received=qty,
        qty_remaining=qty,
        party=party or "",
        created_by=user.id if user else None,
    )
    db.add(batch)
    return batch


def deplete_fefo(db: Session, *, item: Item, qty: float) -> None:
    """Reduce batch quantities First-Expired-First-Out.

    Order: nearest expiry first (non-null), then undated batches by receipt
    date. Untracked legacy stock beyond batch coverage is simply ignored (the
    cached Item.quantity remains the authoritative ledger total).
    """
    remaining = float(qty)
    batches = db.query(Batch).filter(Batch.item_id == item.id, Batch.qty_remaining > 0).all()
    batches.sort(key=lambda b: (b.expiry_date is None, b.expiry_date or date.max, b.created_at))
    for b in batches:
        if remaining <= 0:
            break
        take = min(b.qty_remaining, remaining)
        b.qty_remaining = round(b.qty_remaining - take, 4)
        remaining -= take

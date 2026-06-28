"""Dashboard aggregates for charts and KPIs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Batch, Category, Item, Movement, User
from .expiry import today


def build_summary(db: Session, center_ids: set[str] | None = None, center_filter: str | None = None) -> dict:
    """Aggregate dashboard data, optionally restricted to a set of centers
    (the viewer's scope) and/or a single selected center."""

    def items_q():
        q = db.query(Item)
        if center_ids is not None:
            q = q.filter(Item.center_id.in_(center_ids or {"__none__"}))
        if center_filter:
            q = q.filter(Item.center_id == center_filter)
        return q

    def movements_q():
        q = db.query(Movement)
        if center_ids is not None:
            q = q.filter(Movement.center_id.in_(center_ids or {"__none__"}))
        if center_filter:
            q = q.filter(Movement.center_id == center_filter)
        return q

    scoped_items_all = items_q().all()
    total_items = len(scoped_items_all)
    total_units = float(sum((i.quantity or 0.0) for i in scoped_items_all))
    total_movements = movements_q().count()
    low_stock = sum(
        1 for i in scoped_items_all if (i.quantity or 0.0) <= (i.min_quantity if i.min_quantity else 5)
    )

    # Expiry KPIs from batches still holding stock.
    def batches_q():
        q = db.query(Batch).filter(Batch.qty_remaining > 0, Batch.expiry_date.isnot(None))
        if center_ids is not None:
            q = q.filter(Batch.center_id.in_(center_ids or {"__none__"}))
        if center_filter:
            q = q.filter(Batch.center_id == center_filter)
        return q

    ref = today()
    expired_units = 0.0
    expiring_soon = 0
    for b in batches_q().all():
        delta = (b.expiry_date - ref).days
        if delta < 0:
            expired_units += b.qty_remaining or 0.0
        elif delta <= 30:
            expiring_soon += 1

    units_in = float(sum((m.quantity or 0.0) for m in movements_q().filter(Movement.type == "in").all()))
    units_out = float(sum((m.quantity or 0.0) for m in movements_q().filter(Movement.type == "out").all()))

    # By category (current stock) within scope.
    by_category = []
    scoped_items = items_q().all()
    cat_map: dict[str, dict] = {}
    cats = {c.id: c for c in db.query(Category).all()}
    for it in scoped_items:
        cat = cats.get(it.category_id)
        key = cat.id if cat else "none"
        bucket = cat_map.setdefault(
            key, {"name": cat.name if cat else "Uncategorized", "kind": cat.kind if cat else "other",
                  "items": 0, "units": 0.0}
        )
        bucket["items"] += 1
        bucket["units"] += it.quantity or 0.0
    by_category.sort(key=lambda x: x["units"], reverse=True)

    # Flow over the last 30 days (per day, in vs out).
    since = datetime.now(timezone.utc) - timedelta(days=30)
    daily: dict[str, dict[str, float]] = {}
    for m in movements_q().filter(Movement.created_at >= since).all():
        day = m.created_at.strftime("%Y-%m-%d") if m.created_at else "?"
        bucket = daily.setdefault(day, {"in": 0.0, "out": 0.0})
        if m.type in ("in", "out"):
            bucket[m.type] += float(m.quantity or 0.0)
    flow = [{"date": d, "in": v["in"], "out": v["out"]} for d, v in sorted(daily.items())]

    # Top items by current stock (within scope).
    top_items = [
        {"name": it.canonical_name, "quantity": it.quantity, "unit": it.unit}
        for it in sorted(scoped_items, key=lambda i: (i.quantity or 0.0), reverse=True)[:10]
    ]

    # Activity by volunteer (last 30 days, within scope).
    vol_counts: dict[str, int] = {}
    for m in movements_q().filter(Movement.created_at >= since).all():
        if m.user_id:
            vol_counts[m.user_id] = vol_counts.get(m.user_id, 0) + 1
    users = {u.id: u.name for u in db.query(User).all()}
    by_volunteer = sorted(
        [{"name": users.get(uid, "—"), "movements": c} for uid, c in vol_counts.items()],
        key=lambda x: x["movements"], reverse=True,
    )[:10]

    recent = [
        m.public()
        for m in movements_q().order_by(Movement.created_at.desc()).limit(15).all()
    ]

    return {
        "totals": {
            "items": int(total_items),
            "units": total_units,
            "movements": int(total_movements),
            "low_stock": int(low_stock),
            "units_in": units_in,
            "units_out": units_out,
            "expired_units": expired_units,
            "expiring_soon": expiring_soon,
        },
        "by_category": by_category,
        "flow": flow,
        "top_items": top_items,
        "by_volunteer": by_volunteer,
        "recent_movements": recent,
    }

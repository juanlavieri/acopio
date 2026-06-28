"""Core inventory operations: categorization, dedup/grouping, movements.

These functions are the single source of truth used by both the REST API and
the AI agent, so an action taken by voice/chat is identical to one taken in the
UI — and is always attributed + audited.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import audit
from ..models import Category, Item, Movement, User
from .llm import get_llm
from .semantic import get_index

# Coarse buckets used across the app.
KINDS = ["food", "water", "medical", "hygiene", "shelter", "clothing", "tools", "baby", "other"]

# Heuristic keyword map for offline categorization (multilingual: ES/EN).
_KEYWORDS: dict[str, list[str]] = {
    "food": ["rice", "arroz", "bean", "frijol", "caraota", "flour", "harina", "pasta", "oil",
             "aceite", "sugar", "azucar", "salt", "sal", "canned", "enlatado", "atun", "tuna",
             "sardina", "leche", "milk", "cereal", "food", "comida", "alimento", "lenteja"],
    "water": ["water", "agua", "bottled", "botella", "purification", "purificacion", "electrolyte",
              "suero", "juice", "jugo", "beverage", "bebida"],
    "medical": ["medic", "medicina", "medicine", "drug", "antibiotic", "antibiotico", "bandage",
                "venda", "gauze", "gasa", "antiseptic", "alcohol", "syringe", "jeringa", "first aid",
                "primeros auxilios", "paracetamol", "ibuprofen", "ibuprofeno", "insulin", "insulina",
                "pill", "pastilla", "vitamin", "vitamina", "mask", "tapaboca", "guante", "glove"],
    "hygiene": ["soap", "jabon", "toothpaste", "pasta dental", "shampoo", "diaper", "panal",
                "sanitary", "toalla sanitaria", "toilet", "papel", "detergent", "detergente",
                "hygiene", "higiene", "cloro", "desinfectante", "disinfectant"],
    "shelter": ["tent", "carpa", "tienda", "blanket", "cobija", "manta", "mattress", "colchon",
                "tarp", "lona", "sleeping", "saco de dormir", "shelter", "refugio"],
    "clothing": ["shirt", "camisa", "pants", "pantalon", "shoe", "zapato", "jacket", "chaqueta",
                 "clothes", "ropa", "sock", "media", "boot", "bota", "underwear", "ropa interior"],
    "tools": ["generator", "planta", "flashlight", "linterna", "battery", "bateria", "pila",
              "tool", "herramienta", "rope", "cuerda", "hammer", "martillo", "nail", "clavo",
              "fuel", "combustible", "gasolina"],
    "baby": ["baby", "bebe", "formula", "infant", "panal", "diaper", "baby food", "compota",
             "pacifier", "chupon", "wipes", "toallitas"],
}


def fingerprint(name: str) -> str:
    """Normalised key for exact-match dedup."""
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9áéíóúñü ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _heuristic_kind(text: str) -> str:
    t = (text or "").lower()
    best_kind, best_hits = "other", 0
    for kind, words in _KEYWORDS.items():
        hits = sum(1 for w in words if w in t)
        if hits > best_hits:
            best_kind, best_hits = kind, hits
    return best_kind


def categorize(db: Session, name: str, description: str = "") -> Category | None:
    """Return the best-fit Category, using the LLM when available."""
    text = f"{name} {description}".strip()
    kind = "other"

    llm = get_llm()
    if llm.enabled:
        cats = db.query(Category).all()
        catalog = "\n".join(f"- {c.kind}: {c.name} ({c.description})" for c in cats)
        result = llm.json(
            system=(
                "You classify humanitarian relief supply items into one coarse category. "
                "Reply with JSON {\"kind\": \"<one of: "
                + ", ".join(KINDS)
                + ">\"}. Choose the single best fit."
            ),
            user=f"Available categories:\n{catalog}\n\nItem: {text}",
        )
        if result and result.get("kind") in KINDS:
            kind = result["kind"]
        else:
            kind = _heuristic_kind(text)
    else:
        kind = _heuristic_kind(text)

    cat = db.query(Category).filter(Category.kind == kind).first()
    if not cat:
        cat = db.query(Category).filter(Category.kind == "other").first()
    return cat


def _dedup_threshold() -> float:
    from ..config import settings

    return 0.86 if settings.ai_enabled else 0.78


def match_item(db: Session, *, name: str, center_id: str | None, barcode: str = "") -> Item | None:
    """Find the existing canonical item that means the same thing, WITHOUT
    creating anything. Matching order (scoped to the center):
    barcode/code → exact normalized name → semantic nearest above threshold.
    """
    name = (name or "").strip()
    barcode = (barcode or "").strip()
    fp = fingerprint(name)

    if barcode:
        q = db.query(Item).filter(Item.barcode == barcode)
        if center_id:
            q = q.filter(Item.center_id == center_id)
        existing = q.first()
        if existing:
            return existing

    if fp:
        q = db.query(Item).filter(Item.fingerprint == fp)
        if center_id:
            q = q.filter(Item.center_id == center_id)
        existing = q.first()
        if existing:
            return existing

    center_item_ids = {
        i.id for i in db.query(Item.id).filter(Item.center_id == center_id).all()
    } if center_id else None
    nid, score = get_index().nearest(name, allowed=center_item_ids)
    if nid and score >= _dedup_threshold():
        return db.get(Item, nid)
    return None


def resolve_or_create_item(
    db: Session,
    *,
    name: str,
    user: User | None,
    center_id: str | None,
    unit: str = "unit",
    description: str = "",
    attributes: dict | None = None,
    category: Category | None = None,
    barcode: str = "",
) -> tuple[Item, bool]:
    """Find an existing canonical item (within the same center) or create one.
    Returns (item, created)."""
    name = (name or "").strip()
    barcode = (barcode or "").strip()
    fp = fingerprint(name)
    index = get_index()

    existing = match_item(db, name=name, center_id=center_id, barcode=barcode)
    if existing:
        if barcode and not existing.barcode:
            existing.barcode = barcode
            db.commit()
        return existing, False

    if category is None:
        category = categorize(db, name, description)
    item = Item(
        canonical_name=name or "Unnamed item",
        description=description or "",
        center_id=center_id,
        unit=unit or "unit",
        fingerprint=fp,
        barcode=barcode,
        attributes=attributes or {},
        category_id=category.id if category else None,
        created_by=user.id if user else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    index.upsert(item.id, f"{item.canonical_name}. {item.description}")
    return item, True


def record_movement(
    db: Session,
    *,
    item: Item,
    type: str,
    quantity: float,
    user: User | None,
    unit: str | None = None,
    party: str = "",
    location: str = "",
    note: str = "",
    reason: str = "",
    expiry_date=None,
    lot_code: str = "",
    source: str = "manual",
) -> Movement:
    """Apply an in/out/adjust movement, update cached stock, manage batches
    (FEFO) and audit it."""
    from .expiry import create_batch, deplete_fefo

    qty = abs(float(quantity))
    if type == "out":
        signed = -qty
    elif type == "adjust":
        signed = float(quantity)  # adjust may be negative
    else:
        type = "in"
        signed = qty

    new_balance = round((item.quantity or 0.0) + signed, 4)
    mv = Movement(
        item_id=item.id,
        center_id=item.center_id,
        type=type,
        quantity=qty if type != "adjust" else abs(float(quantity)),
        unit=unit or item.unit,
        signed_quantity=signed,
        balance_after=new_balance,
        party=party or "",
        location=location or "",
        note=note or "",
        reason=reason or "",
        expiry_date=expiry_date,
        lot_code=lot_code or "",
        source=source,
        user_id=user.id if user else None,
    )
    item.quantity = new_balance

    # Batch tracking: increases create a batch; decreases deplete FEFO.
    if type == "in":
        create_batch(db, item=item, qty=qty, expiry=expiry_date, lot=lot_code, party=party, user=user)
    elif type == "out":
        deplete_fefo(db, item=item, qty=qty)
    elif type == "adjust" and signed > 0:
        create_batch(db, item=item, qty=signed, expiry=expiry_date, lot=lot_code, party=party, user=user)
    elif type == "adjust" and signed < 0:
        deplete_fefo(db, item=item, qty=abs(signed))

    db.add(mv)
    db.commit()
    db.refresh(mv)

    audit(
        db,
        user,
        action=f"movement.{type}",
        entity_type="movement",
        entity_id=mv.id,
        detail={
            "item_id": item.id,
            "item_name": item.canonical_name,
            "quantity": qty,
            "signed": signed,
            "balance_after": new_balance,
            "reason": reason,
            "source": source,
            "party": party,
        },
    )
    return mv


def correct_stock(db: Session, *, item: Item, target: float, user: User | None,
                  note: str = "", source: str = "manual") -> Movement | None:
    """Set an item's stock to the correct absolute value via a logged adjustment."""
    delta = round(float(target) - float(item.quantity or 0.0), 4)
    if abs(delta) < 1e-9:
        return None
    return record_movement(
        db, item=item, type="adjust", quantity=delta, user=user, reason="correction",
        note=note or f"Corrected stock to {float(target):g}", source=source,
    )


def void_movement(db: Session, *, movement: Movement, user: User | None, source: str = "manual") -> Movement | None:
    """Reverse a movement (undo a mistake) with a compensating adjustment.

    The original record is kept (audit integrity) and flagged voided.
    """
    if movement.voided:
        return None
    reverse = -float(movement.signed_quantity or 0.0)
    mv = record_movement(
        db, item=movement.item, type="adjust", quantity=reverse, user=user, reason="correction",
        note=f"Reversed entry from {movement.created_at:%Y-%m-%d}" if movement.created_at else "Reversed entry",
        source=source,
    )
    movement.voided = True
    db.commit()
    return mv


def current_stock_total(db: Session) -> float:
    return float(db.query(func.coalesce(func.sum(Item.quantity), 0.0)).scalar() or 0.0)


def reindex_missing(db: Session) -> int:
    """Rebuild semantic vectors for items absent from the index.

    The vector index is a cache (it may live on ephemeral storage); the DB is
    the source of truth. On boot we backfill any items that lost their vector so
    dedup + semantic search keep working after a redeploy.
    """
    index = get_index()
    missing = 0
    for item in db.query(Item).all():
        if item.id not in index._vectors:  # noqa: SLF001  (intentional cache check)
            index.upsert(item.id, f"{item.canonical_name}. {item.description}")
            missing += 1
    return missing

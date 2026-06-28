"""SQLAlchemy ORM models for Acopio.

Design goals:
- Every stock movement is attributable to a volunteer (accountability).
- An immutable audit log records every meaningful action.
- A canonical ``Item`` represents a deduplicated supply (e.g. "Rice 1kg"),
  while ``Movement`` rows record each in/out event. Current stock = sum of
  signed movement quantities (cached on the item for fast reads).
- Flexible schema: volunteers/agent can add fields to items (``CustomField``)
  and even spin up new lightweight tables (``CustomTable`` + ``CustomRecord``)
  WITHOUT running raw DDL — safe and reversible.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("reg"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="Venezuela")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def public(self, centers: int | None = None) -> dict:
        return {"id": self.id, "name": self.name, "country": self.country, "centers": centers}


class Center(Base):
    """A collection center (centro de acopio)."""

    __tablename__ = "centers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("ctr"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True, index=True)
    location: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    region: Mapped[Region | None] = relationship()

    def public(self, extra: dict | None = None) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "region_id": self.region_id,
            "region": self.region.name if self.region else None,
            "location": self.location,
        }
        if extra:
            d.update(extra)
        return d


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("usr"))
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Role hierarchy: country_manager > regional_manager > center_manager > volunteer
    role: Mapped[str] = mapped_column(String, default="volunteer")
    # Scope: managers are scoped to a region/center; volunteers to a center.
    region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True, index=True)
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    region: Mapped[Region | None] = relationship("Region", foreign_keys=[region_id])
    center: Mapped[Center | None] = relationship("Center", foreign_keys=[center_id])

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "region_id": self.region_id,
            "region": self.region.name if self.region else None,
            "center_id": self.center_id,
            "center": self.center.name if self.center else None,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionToken(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("cat"))
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Coarse machine-friendly bucket: food | water | medical | hygiene |
    # shelter | clothing | tools | baby | other
    kind: Mapped[str] = mapped_column(String, default="other", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "description": self.description}


class Item(Base):
    """A canonical, deduplicated supply line."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("item"))
    canonical_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # Stock is tracked per collection center.
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String, default="unit")  # unit of measure
    # Cached current stock = SUM(signed movement quantities).
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    # Reorder threshold (par level). 0 => use the default low-stock threshold.
    min_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    # Optional barcode / SKU for fast scanning & lookup.
    barcode: Mapped[str] = mapped_column(String, default="", index=True)
    # Normalised key used for fast dedup lookups (lowercased/cleaned name).
    fingerprint: Mapped[str] = mapped_column(String, index=True, default="")
    # Flexible attributes (supplier, brand, expiry, plus any CustomField values).
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    category: Mapped[Category | None] = relationship()
    center: Mapped["Center | None"] = relationship()

    def public(self, category_name: str | None = None) -> dict:
        return {
            "id": self.id,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "center_id": self.center_id,
            "center": self.center.name if self.center else None,
            "category_id": self.category_id,
            "category": category_name or (self.category.name if self.category else None),
            "category_kind": self.category.kind if self.category else None,
            "unit": self.unit,
            "quantity": self.quantity,
            "min_quantity": self.min_quantity or 0.0,
            "low_stock": (self.quantity or 0.0) <= (self.min_quantity if self.min_quantity else 5),
            "barcode": self.barcode or "",
            "attributes": self.attributes or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Movement(Base):
    """A single stock event: intake (in), dispatch (out) or adjustment."""

    __tablename__ = "movements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("mov"))
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), index=True)
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String, default="in")  # in | out | adjust
    quantity: Mapped[float] = mapped_column(Float, default=0.0)  # always positive magnitude
    unit: Mapped[str] = mapped_column(String, default="unit")
    # Signed delta actually applied to stock (negative for "out").
    signed_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    balance_after: Mapped[float] = mapped_column(Float, default=0.0)
    location: Mapped[str] = mapped_column(String, default="")
    party: Mapped[str] = mapped_column(String, default="")  # supplier (in) or recipient (out)
    note: Mapped[str] = mapped_column(Text, default="")
    # Reason code: in=donation/purchase/transfer_in/return; out=distributed/
    # transferred/damaged/expired/lost; adjust=count/correction.
    reason: Mapped[str] = mapped_column(String, default="")
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lot_code: Mapped[str] = mapped_column(String, default="")
    # Set true when this movement has been reversed/undone by a correction.
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    # For dispatches/decreases: the batches (expiry/lot/qty) consumed, so an
    # undo can restore stock with the exact original expiry dates.
    batch_refs: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | upload | agent
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    item: Mapped[Item] = relationship()
    user: Mapped[User | None] = relationship()

    def public(self) -> dict:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.canonical_name if self.item else None,
            "center_id": self.center_id,
            "type": self.type,
            "quantity": self.quantity,
            "unit": self.unit,
            "signed_quantity": self.signed_quantity,
            "balance_after": self.balance_after,
            "location": self.location,
            "party": self.party,
            "note": self.note,
            "reason": self.reason or "",
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "lot_code": self.lot_code or "",
            "voided": bool(self.voided),
            "source": self.source,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("aud"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, default="")
    entity_id: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped[User | None] = relationship()

    def public(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "detail": self.detail or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("upl"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|processing|done|error
    # "add" = each row is a new arrival; "sync" = sheet is the full current stock.
    mode: Mapped[str] = mapped_column(String, default="add")
    # SHA-256 of the uploaded bytes, to detect identical re-uploads.
    content_hash: Mapped[str] = mapped_column(String, default="", index=True)
    # Target center for a sync, and the proposed reconciliation plan (preview).
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    rows_detected: Mapped[int] = mapped_column(Integer, default=0)
    items_created: Mapped[int] = mapped_column(Integer, default=0)
    items_matched: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship()

    def public(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "mode": self.mode or "add",
            "rows_detected": self.rows_detected,
            "items_created": self.items_created,
            "items_matched": self.items_matched,
            "summary": self.summary,
            "mapping": self.mapping or {},
            "error": self.error,
            "user_name": self.user.name if self.user else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CustomField(Base):
    """A volunteer/agent-added field (a.k.a. "column") on items.

    Values live inside ``Item.attributes`` keyed by ``key``; this table is the
    registry/schema so the UI and agent know which extra fields exist.
    """

    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("entity", "key", name="uq_customfield_entity_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("fld"))
    entity: Mapped[str] = mapped_column(String, default="item")  # item | movement
    key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="text")  # text|number|date|boolean
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def public(self) -> dict:
        return {"id": self.id, "entity": self.entity, "key": self.key, "label": self.label, "type": self.type}


class CustomTable(Base):
    """A lightweight, agent/volunteer-created table (schema as JSON)."""

    __tablename__ = "custom_tables"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("tbl"))
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, default="")
    schema: Mapped[list] = mapped_column(JSON, default=list)  # [{key,label,type}]
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "label": self.label, "schema": self.schema or []}


class Batch(Base):
    """A received lot of an item with its own expiry date (enables FEFO).

    Stock-on-hand for an item = sum of batch ``qty_remaining`` (for tracked
    intake) reconciled with the cached ``Item.quantity`` ledger total.
    """

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("btc"))
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), index=True)
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    # The intake movement that created this batch (enables precise undo).
    movement_id: Mapped[str | None] = mapped_column(ForeignKey("movements.id"), nullable=True, index=True)
    lot_code: Mapped[str] = mapped_column(String, default="")
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    qty_received: Mapped[float] = mapped_column(Float, default=0.0)
    qty_remaining: Mapped[float] = mapped_column(Float, default=0.0)
    party: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    item: Mapped[Item] = relationship()

    def public(self) -> dict:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.canonical_name if self.item else None,
            "unit": self.item.unit if self.item else "unit",
            "lot_code": self.lot_code,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "qty_received": self.qty_received,
            "qty_remaining": self.qty_remaining,
            "party": self.party,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Need(Base):
    """A field request / requisition for supplies (demand side)."""

    __tablename__ = "needs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("need"))
    center_id: Mapped[str | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    item_name: Mapped[str] = mapped_column(String, nullable=False)
    category_kind: Mapped[str] = mapped_column(String, default="other")
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    fulfilled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String, default="unit")
    priority: Mapped[str] = mapped_column(String, default="normal")  # low|normal|high|urgent
    status: Mapped[str] = mapped_column(String, default="open")  # open|partial|fulfilled|cancelled
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    center: Mapped[Center | None] = relationship()
    requester: Mapped[User | None] = relationship(foreign_keys=[requested_by])

    def public(self) -> dict:
        return {
            "id": self.id,
            "center_id": self.center_id,
            "center": self.center.name if self.center else None,
            "item_name": self.item_name,
            "category_kind": self.category_kind,
            "quantity": self.quantity,
            "fulfilled_quantity": self.fulfilled_quantity,
            "unit": self.unit,
            "priority": self.priority,
            "status": self.status,
            "needed_by": self.needed_by.isoformat() if self.needed_by else None,
            "note": self.note,
            "requested_by": self.requested_by,
            "requester": self.requester.name if self.requester else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CustomRecord(Base):
    __tablename__ = "custom_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uuid("rec"))
    table_id: Mapped[str] = mapped_column(ForeignKey("custom_tables.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def public(self) -> dict:
        return {
            "id": self.id,
            "table_id": self.table_id,
            "data": self.data or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

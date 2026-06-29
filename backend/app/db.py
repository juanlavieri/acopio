"""Database engine + session management (SQLAlchemy 2.x)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.sqlalchemy_url.startswith("sqlite")

engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    # SQLite needs this when used across FastAPI's threadpool.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables and seed baseline data. Safe to call repeatedly."""
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()

    from .auth import hash_password  # lazy import avoids circular import
    from .models import Category, Center, Region, Tenant, User

    with SessionLocal() as db:
        if db.query(Category).count() == 0:
            for name, kind, desc in DEFAULT_CATEGORIES:
                db.add(Category(name=name, kind=kind, description=desc))
            db.commit()

        # Seed a default tenant + region + center on a fresh database.
        if db.query(Region).count() == 0 and db.query(Tenant).count() == 0:
            tenant = Tenant(name=settings.default_region or settings.default_country, country=settings.default_country)
            db.add(tenant)
            db.flush()
            region = Region(name=settings.default_region, country=settings.default_country, tenant_id=tenant.id)
            db.add(region)
            db.flush()
            db.add(Center(name=settings.default_center, region_id=region.id, location=settings.default_country))
            db.commit()

        # Bootstrap the first country manager (env), once, into the first tenant.
        if (
            settings.bootstrap_admin_email
            and settings.bootstrap_admin_password
            and db.query(User).filter(User.role == "country_manager").count() == 0
        ):
            email = settings.bootstrap_admin_email.lower().strip()
            if not db.query(User).filter(User.email == email).first():
                tenant = db.query(Tenant).order_by(Tenant.created_at).first()
                db.add(User(
                    email=email, name=(settings.bootstrap_admin_name or email).strip(),
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="country_manager", tenant_id=tenant.id if tenant else None,
                ))
                db.commit()

        # Bootstrap the super admin (env), once.
        if (
            settings.bootstrap_superadmin_email
            and settings.bootstrap_superadmin_password
            and db.query(User).filter(User.role == "super_admin").count() == 0
        ):
            email = settings.bootstrap_superadmin_email.lower().strip()
            if not db.query(User).filter(User.email == email).first():
                db.add(User(
                    email=email, name=(settings.bootstrap_superadmin_name or "Super Admin").strip(),
                    password_hash=hash_password(settings.bootstrap_superadmin_password),
                    role="super_admin", tenant_id=None,
                ))
                db.commit()

        _backfill_tenancy(db)


def _backfill_tenancy(db) -> None:
    """Assign legacy regions/users (created before multi-tenancy) to a tenant."""
    from .models import Region, Tenant, User

    legacy_regions = db.query(Region).filter(Region.tenant_id.is_(None)).all()
    legacy_users = db.query(User).filter(
        User.tenant_id.is_(None), User.role != "super_admin"
    ).all()
    if not legacy_regions and not legacy_users:
        return

    tenant = db.query(Tenant).order_by(Tenant.created_at).first()
    if not tenant:
        tenant = Tenant(name=settings.default_region or settings.default_country or "Default",
                        country=settings.default_country)
        db.add(tenant)
        db.flush()
    for r in legacy_regions:
        r.tenant_id = tenant.id
    for u in legacy_users:
        u.tenant_id = tenant.id
    db.commit()


# New columns added across versions. Keep additive + nullable so a plain
# ALTER TABLE works on both SQLite and Postgres without Alembic.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "users": {"region_id": "VARCHAR", "center_id": "VARCHAR", "tenant_id": "VARCHAR"},
    "regions": {"tenant_id": "VARCHAR"},
    "items": {"center_id": "VARCHAR", "min_quantity": "FLOAT", "barcode": "VARCHAR"},
    "movements": {
        "center_id": "VARCHAR",
        "reason": "VARCHAR",
        "expiry_date": "DATE",
        "lot_code": "VARCHAR",
        "voided": "BOOLEAN",
        "batch_refs": "JSON",
    },
    "uploads": {"mode": "VARCHAR", "content_hash": "VARCHAR", "center_id": "VARCHAR", "plan": "JSON"},
    "batches": {"movement_id": "VARCHAR"},
}


def _apply_additive_migrations() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for col, sqltype in cols.items():
                if col not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {sqltype}'))


DEFAULT_CATEGORIES: list[tuple[str, str, str]] = [
    ("Food & Non-perishables", "food", "Rice, canned goods, flour, oil, baby formula, etc."),
    ("Water & Beverages", "water", "Bottled water, purification tablets, electrolytes."),
    ("Medical & First Aid", "medical", "Medicines, bandages, antiseptics, medical equipment."),
    ("Hygiene & Personal Care", "hygiene", "Soap, toothpaste, diapers, sanitary products."),
    ("Shelter & Bedding", "shelter", "Tents, blankets, mattresses, tarps."),
    ("Clothing & Footwear", "clothing", "Clothes, shoes, jackets for all ages."),
    ("Tools & Equipment", "tools", "Generators, flashlights, batteries, hardware."),
    ("Baby & Child Care", "baby", "Diapers, formula, baby food, toys."),
    ("Uncategorized", "other", "Items pending classification."),
]

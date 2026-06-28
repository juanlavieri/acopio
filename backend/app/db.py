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

    # Seed default relief categories on first boot.
    from .models import Category, Center, Region, User

    with SessionLocal() as db:
        if db.query(Category).count() == 0:
            for name, kind, desc in DEFAULT_CATEGORIES:
                db.add(Category(name=name, kind=kind, description=desc))
            db.commit()

        # Seed a default region + center so the app is usable on first run.
        if db.query(Region).count() == 0:
            region = Region(name=settings.default_region, country=settings.default_country)
            db.add(region)
            db.flush()
            db.add(Center(name=settings.default_center, region_id=region.id, location=settings.default_country))
            db.commit()

        # Optional: bootstrap the first country manager from env vars, once.
        if (
            settings.bootstrap_admin_email
            and settings.bootstrap_admin_password
            and db.query(User).count() == 0
        ):
            from .auth import hash_password  # lazy import avoids circular import

            email = settings.bootstrap_admin_email.lower().strip()
            db.add(
                User(
                    email=email,
                    name=(settings.bootstrap_admin_name or email).strip(),
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="country_manager",
                )
            )
            db.commit()


# New columns added across versions. Keep additive + nullable so a plain
# ALTER TABLE works on both SQLite and Postgres without Alembic.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "users": {"region_id": "VARCHAR", "center_id": "VARCHAR"},
    "items": {"center_id": "VARCHAR", "min_quantity": "FLOAT", "barcode": "VARCHAR"},
    "movements": {
        "center_id": "VARCHAR",
        "reason": "VARCHAR",
        "expiry_date": "DATE",
        "lot_code": "VARCHAR",
    },
    "uploads": {"mode": "VARCHAR", "content_hash": "VARCHAR"},
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

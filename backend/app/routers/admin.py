"""Super-admin cross-organization overview."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_super_admin
from ..db import get_db
from ..models import Tenant, User
from ..scope import tenant_center_ids
from ..services.dashboard import build_summary

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin: User = Depends(require_super_admin)):
    summary = build_summary(db)  # global rollup across all organizations
    orgs = []
    for t in db.query(Tenant).order_by(Tenant.name).all():
        center_ids = tenant_center_ids(db, t.id)
        totals = build_summary(db, center_ids=center_ids)["totals"]
        users = db.query(User).filter(User.tenant_id == t.id).count()
        managers = [
            u.name for u in db.query(User).filter(User.tenant_id == t.id, User.role == "country_manager").all()
        ]
        orgs.append({
            "id": t.id, "name": t.name, "country": t.country,
            "centers": len(center_ids), "users": users, "managers": managers, "totals": totals,
        })
    orgs.sort(key=lambda o: o["totals"]["units"], reverse=True)
    return {"summary": summary, "organizations": orgs, "tenant_count": len(orgs)}

"""Dashboard data endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..scope import visible_center_ids
from ..services.dashboard import build_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(
    center_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    vis = visible_center_ids(db, user)
    if center_id and vis is not None and center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That center is outside your scope.")
    return build_summary(db, center_ids=vis, center_filter=center_id)

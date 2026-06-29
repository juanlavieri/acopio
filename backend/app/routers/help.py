"""In-app how-to guide."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..help import help_sections
from ..models import User

router = APIRouter(prefix="/api", tags=["help"])


@router.get("/help")
def get_help(lang: str = Query(default="en"), _user: User = Depends(get_current_user)):
    return {"sections": help_sections(lang)}

"""AI assistant (chat) endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import User
from ..services.agent import run_agent

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str
    history: list[ChatTurn] = []
    center_id: str | None = None


@router.get("/status")
def status_(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.llm import resolve_tenant_key

    return {"ai_enabled": bool(resolve_tenant_key(db, user)), "model": settings.openai_model}


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    history = [{"role": t.role, "content": t.content} for t in body.history]
    return run_agent(db, user, body.message, history, center_id=body.center_id)

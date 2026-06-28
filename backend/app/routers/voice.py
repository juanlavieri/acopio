"""Voice transcription endpoint (OpenAI Whisper)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import User
from ..services.llm import get_llm

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    _user: User = Depends(get_current_user),
    _db: Session = Depends(get_db),
):
    if not settings.ai_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Server-side transcription needs an OpenAI key. Use the browser mic fallback.",
        )
    data = await audio.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio.")
    text = get_llm().transcribe(audio.filename or "audio.webm", data)
    if text is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription failed.")
    return {"text": text}

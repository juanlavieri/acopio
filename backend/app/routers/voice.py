"""Voice transcription endpoint (OpenAI Whisper)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.llm import llm_for

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    llm = llm_for(db, user)
    if not llm.enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Your organization has no OpenAI key. Use the browser mic fallback or add a key.",
        )
    data = await audio.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio.")
    text = llm.transcribe(audio.filename or "audio.webm", data)
    if text is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription failed.")
    return {"text": text}

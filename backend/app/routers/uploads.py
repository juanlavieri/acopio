"""Spreadsheet upload + normalization endpoint."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth import audit, get_current_user
from ..db import get_db
from ..models import Upload, User
from ..scope import resolve_target_center
from ..services.normalize import normalize_upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    center_id: str | None = Form(default=None),
    mode: str = Form(default="add"),
    force: bool = Form(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file.")
    if mode not in {"add", "sync"}:
        mode = "add"

    try:
        target_center = resolve_target_center(db, user, center_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    content_hash = hashlib.sha256(data).hexdigest()

    # Identical file already imported into this center? Skip unless forced.
    if not force:
        prev = (
            db.query(Upload)
            .filter(Upload.content_hash == content_hash, Upload.status == "done")
            .order_by(Upload.created_at.desc())
            .first()
        )
        if prev:
            return {
                "duplicate": True,
                "previous": prev.public(),
                "message": "This exact file was already imported.",
            }

    upload = Upload(
        user_id=user.id, filename=file.filename or "upload", status="processing",
        mode=mode, content_hash=content_hash,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    try:
        result = normalize_upload(
            db, upload=upload, filename=file.filename or "upload", data=data,
            user=user, center_id=target_center, mode=mode,
        )
    except Exception as e:
        upload.status = "error"
        upload.error = str(e)
        db.commit()
        audit(db, user, "upload.error", "upload", upload.id, {"error": str(e)})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not process file: {e}")

    audit(db, user, "upload.process", "upload", upload.id, result)
    return {"upload": upload.public(), "result": result}


@router.get("")
def list_uploads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..scope import visible_center_ids

    vis = visible_center_ids(db, user)
    uploads = db.query(Upload).order_by(Upload.created_at.desc()).limit(100).all()
    if vis is not None:
        allowed = {u.id for u in db.query(User).all() if (u.center_id in vis) or u.id == user.id}
        uploads = [u for u in uploads if u.user_id in allowed]
    return {"uploads": [u.public() for u in uploads[:50]]}

"""Spreadsheet upload + normalization.

- mode="add": each row is a new arrival → applied immediately.
- mode="sync": returns an editable reconciliation PREVIEW; the user approves it
  via /commit, which applies only the deltas (no double counting).
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, get_current_user
from ..db import get_db
from ..models import Upload, User
from ..scope import resolve_target_center, visible_center_ids
from ..services.normalize import apply_sync, normalize_upload, preview_sync

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
    filename = file.filename or "upload"

    # Identical file already imported (and applied)? Skip unless forced.
    if not force:
        prev = (
            db.query(Upload)
            .filter(Upload.content_hash == content_hash, Upload.status == "done")
            .order_by(Upload.created_at.desc())
            .first()
        )
        if prev:
            return {"duplicate": True, "previous": prev.public(), "message": "This exact file was already imported."}

    # SYNC: build a preview the user can review/edit and then commit.
    if mode == "sync":
        try:
            preview = preview_sync(db, filename=filename, data=data, center_id=target_center, user=user)
        except Exception as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not process file: {e}")
        upload = Upload(
            user_id=user.id, filename=filename, status="preview", mode="sync",
            content_hash=content_hash, center_id=target_center, plan=preview["plan"],
            rows_detected=preview["rows"], mapping={"sheets": preview["mappings"]},
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        return {"preview": True, "upload": upload.public(), "plan": preview["plan"],
                "mapping": upload.mapping, "rows": preview["rows"]}

    # ADD: apply immediately.
    upload = Upload(user_id=user.id, filename=filename, status="processing", mode="add", content_hash=content_hash)
    db.add(upload)
    db.commit()
    db.refresh(upload)
    try:
        result = normalize_upload(db, upload=upload, filename=filename, data=data, user=user,
                                  center_id=target_center, mode="add")
    except Exception as e:
        upload.status = "error"
        upload.error = str(e)
        db.commit()
        audit(db, user, "upload.error", "upload", upload.id, {"error": str(e)})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not process file: {e}")

    audit(db, user, "upload.process", "upload", upload.id, result)
    return {"upload": upload.public(), "result": result}


class PlanEntry(BaseModel):
    item_id: str | None = None
    name: str = ""
    barcode: str = ""
    unit: str = "unit"
    target: float = 0.0
    expiry: str | None = None


class CommitIn(BaseModel):
    items: list[PlanEntry]


def _scoped_upload(db: Session, user: User, upload_id: str) -> Upload:
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found.")
    vis = visible_center_ids(db, user)
    if vis is not None and upload.center_id not in vis:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your scope.")
    return upload


@router.post("/{upload_id}/commit")
def commit_upload(upload_id: str, body: CommitIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    upload = _scoped_upload(db, user, upload_id)
    if upload.status != "preview":
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload is not awaiting approval.")

    entries = [e.model_dump() for e in body.items]
    result = apply_sync(db, entries=entries, user=user, center_id=upload.center_id, filename=upload.filename)

    upload.status = "done"
    upload.items_created = result["created"]
    upload.items_matched = max(result["items"] - result["created"], 0)
    upload.summary = result["summary"]
    db.commit()
    audit(db, user, "upload.commit", "upload", upload.id, result)
    return {"upload": upload.public(), "result": result}


@router.post("/{upload_id}/cancel")
def cancel_upload(upload_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    upload = _scoped_upload(db, user, upload_id)
    if upload.status == "preview":
        db.delete(upload)
        db.commit()
    return {"ok": True}


@router.get("")
def list_uploads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vis = visible_center_ids(db, user)
    uploads = db.query(Upload).filter(Upload.status != "preview").order_by(Upload.created_at.desc()).limit(100).all()
    if vis is not None:
        allowed = {u.id for u in db.query(User).all() if (u.center_id in vis) or u.id == user.id}
        uploads = [u for u in uploads if u.user_id in allowed]
    return {"uploads": [u.public() for u in uploads[:50]]}

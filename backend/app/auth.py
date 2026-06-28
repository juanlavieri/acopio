"""Authentication: password hashing, sessions, and FastAPI dependencies.

Custom + dependency-free (mirrors crypto-pay-poc/server/accounts.js) but using
PBKDF2-HMAC-SHA256 from the standard library, which is safe and portable.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuditLog, SessionToken, User

_PBKDF2_ROUNDS = 200_000
_SESSION_TTL = timedelta(days=7)


# --- password hashing ----------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# --- sessions ------------------------------------------------------------
def create_session(db: Session, user: User) -> str:
    token = "sess_" + secrets.token_urlsafe(32)
    db.add(
        SessionToken(
            token=token,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + _SESSION_TTL,
        )
    )
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    db.query(SessionToken).filter(SessionToken.token == token).delete()
    db.commit()


# --- audit ---------------------------------------------------------------
def audit(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
        )
    )
    db.commit()


# --- dependencies --------------------------------------------------------
def _token_from_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _token_from_header(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    sess = db.get(SessionToken, token)
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    user = db.get(User, sess.user_id)
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


def require_org_manager(user: User = Depends(get_current_user)) -> User:
    """Any manager level (center_manager and above) may manage the org."""
    from .scope import can_manage_org

    if not can_manage_org(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager privileges required")
    return user


def require_country_manager(user: User = Depends(get_current_user)) -> User:
    from .scope import COUNTRY_MANAGER

    if user.role != COUNTRY_MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Country manager privileges required")
    return user

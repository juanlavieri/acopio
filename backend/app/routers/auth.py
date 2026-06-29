"""Authentication routes (login, bootstrap registration, profile)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..validators import EmailField

from ..auth import (
    audit,
    create_session,
    get_current_user,
    hash_password,
    revoke_session,
    verify_password,
)
from ..db import get_db
from ..models import SessionToken, Tenant, User
from ..scope import COUNTRY_MANAGER

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailField
    name: str
    password: str


class LoginIn(BaseModel):
    email: EmailField
    password: str


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Bootstrap registration.

    Only allowed for the very first account, which becomes the country manager.
    All other accounts are created by a manager (see /api/org/users).
    """
    if db.query(User).count() > 0:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Self-registration is closed. Ask your manager to create your account.",
        )
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters.")

    email = body.email.lower().strip()
    # The bootstrap account owns the seeded tenant (or a new one).
    tenant = db.query(Tenant).order_by(Tenant.created_at).first()
    if not tenant:
        tenant = Tenant(name=email.split("@")[0], country="")
        db.add(tenant)
        db.flush()
    user = User(
        email=email,
        name=body.name.strip() or email,
        password_hash=hash_password(body.password),
        role=COUNTRY_MANAGER,
        tenant_id=tenant.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user, "auth.register", "user", user.id, {"role": COUNTRY_MANAGER})

    token = create_session(db, user)
    return {"token": token, "user": user.public()}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if not user.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")
    token = create_session(db, user)
    audit(db, user, "auth.login", "user", user.id)
    return {"token": token, "user": user.public()}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    if authorization:
        token = authorization.split(" ", 1)[-1].strip()
        revoke_session(db, token)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user.public()}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be at least 8 characters.")

    user.password_hash = hash_password(body.new_password)
    db.commit()

    # Revoke all OTHER sessions for security (keep the current one).
    current = authorization.split(" ", 1)[-1].strip() if authorization else ""
    db.query(SessionToken).filter(SessionToken.user_id == user.id, SessionToken.token != current).delete()
    db.commit()

    audit(db, user, "auth.change_password", "user", user.id)
    return {"ok": True}


@router.get("/bootstrap")
def bootstrap_status(db: Session = Depends(get_db)):
    """Public: lets the login screen know whether to show 'create first account'."""
    return {"needs_bootstrap": db.query(User).count() == 0}

"""Lightweight field validators (no external email-validator dependency)."""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    return v


# Use in place of pydantic's EmailStr: normalizes + validates basic format.
EmailField = Annotated[str, AfterValidator(_normalize_email)]

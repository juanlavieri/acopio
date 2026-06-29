"""Thin OpenAI wrapper used for normalization, the agent and voice.

The OpenAI key is resolved PER ORGANIZATION (tenant): a tenant's own key, else
the platform key if the tenant is allowed, else AI is disabled for that tenant.
Everything degrades gracefully: with no key, methods return None and callers
fall back to offline heuristics.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings


def resolve_tenant_key(db, user) -> str | None:
    """The OpenAI key this user's organization may use (or None)."""
    from ..models import Tenant
    from ..scope import SUPER_ADMIN

    if user is None:
        return None
    if user.role == SUPER_ADMIN:
        return settings.openai_api_key
    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id else None
    if not tenant:
        return None
    if tenant.openai_api_key:
        return tenant.openai_api_key
    if tenant.use_platform_key and settings.openai_api_key:
        return settings.openai_api_key
    return None


class LLM:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = None
        if api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=api_key)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # --- chat -----------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> Any:
        """Return the raw OpenAI message object (or None if disabled)."""
        if not self._client:
            return None
        kwargs: dict[str, Any] = {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message

    def json(self, system: str, user: str, *, temperature: float = 0.1) -> dict | None:
        """Convenience: ask for a single JSON object and parse it."""
        msg = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            json_mode=True,
        )
        if not msg or not msg.content:
            return None
        try:
            return json.loads(msg.content)
        except Exception:
            return None

    # --- voice ----------------------------------------------------------
    def transcribe(self, filename: str, data: bytes) -> str | None:
        if not self._client:
            return None
        import io

        buf = io.BytesIO(data)
        buf.name = filename or "audio.webm"
        try:
            resp = self._client.audio.transcriptions.create(
                model=settings.openai_transcribe_model,
                file=buf,
            )
            return getattr(resp, "text", None)
        except Exception:
            return None


_cache: dict[str, LLM] = {}


def get_llm(api_key: str | None = None) -> LLM:
    """Cached LLM client per API key (empty string = disabled)."""
    key = api_key or ""
    if key not in _cache:
        _cache[key] = LLM(api_key)
    return _cache[key]


def llm_for(db, user) -> LLM:
    """LLM for the user's organization (respects per-tenant key gating)."""
    return get_llm(resolve_tenant_key(db, user))

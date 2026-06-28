"""Thin OpenAI wrapper used for normalization, the agent and voice.

Everything degrades gracefully: if no API key is configured every method
returns a safe empty/None result and callers fall back to offline heuristics.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings


class LLM:
    def __init__(self) -> None:
        self._client = None
        if settings.ai_enabled:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
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


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm

"""OpenAI-compatible chat-completions client for IMPACTMAP Copilot.

Only environment configuration is used for credentials. The key is never logged,
returned by any endpoint, or accepted from the browser. Providers that expose an
OpenAI-compatible ``/chat/completions`` endpoint work by changing
``LLM_BASE_URL`` and ``LLM_MODEL``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import logger


class LLMError(RuntimeError):
    """A safe, user-facing model failure that never contains credentials."""


@dataclass
class LLMResult:
    content: str
    model: str
    provider: str

    @property
    def ai_enabled(self) -> bool:
        return True


class LLMClient:
    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.provider = (provider or settings.LLM_PROVIDER).strip()
        self.api_key = settings.LLM_API_KEY if api_key is None else api_key
        self.base_url = (base_url or settings.LLM_BASE_URL).strip().rstrip("/")
        self.model = (model or settings.LLM_MODEL).strip()
        self.timeout_seconds = timeout_seconds or settings.LLM_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        """Whether a key is present (used for status messaging)."""
        return bool(self.api_key)

    @property
    def enabled(self) -> bool:
        provider = self.provider.lower()
        if provider in {"none", "disabled", "offline"} or not self.base_url or not self.model:
            return False
        if self.api_key:
            return True
        # Local OpenAI-compatible servers commonly run without a key.
        return provider in {"ollama", "lmstudio", "local", "ollama-compatible"}

    def status(self) -> dict:
        return {
            "ai_enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "key_configured": self.configured,
            "retrieval": "BM25 over files/symbols plus dependency-graph expansion",
            "max_context_chars": settings.LLM_MAX_CONTEXT_CHARS,
            "retrieval_top_k": settings.COPILOT_RETRIEVAL_TOP_K,
            "max_history_messages": settings.COPILOT_MAX_HISTORY_MESSAGES,
            "setup": (
                "Configure LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL, "
                "LLM_PROVIDER) in backend/.env to enable model-written answers. "
                "Without a key, Copilot still answers from local static evidence."
            ),
        }

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.15,
    ) -> LLMResult:
        if not self.enabled:
            raise LLMError("No language-model provider is configured")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self._endpoint(), headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"The model provider did not respond within {self.timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the model provider: {exc}") from exc

        if response.status_code >= 400:
            detail = _safe_error_detail(response, self.api_key)
            logger.warning(
                "Copilot model request failed: status=%s detail=%s",
                response.status_code,
                detail,
            )
            raise LLMError(
                f"Model provider returned HTTP {response.status_code}: {detail}"
            )

        try:
            payload_json = response.json()
            content = payload_json["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The model provider returned an invalid response payload") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError("The model provider returned an empty response")
        return LLMResult(
            content=content.strip(),
            model=self.model,
            provider=self.provider,
        )


_KEY_PATTERN = re.compile(r"\b(?:sk|key|api[_-]?key)[-_][A-Za-z0-9*]{4,}\b", re.IGNORECASE)


def _safe_error_detail(response: httpx.Response, api_key: str = "") -> str:
    """Extract a short provider message without echoing credentials.

    Authentication failures are collapsed to a generic message because some
    providers echo a partially masked key back in the error body.
    """
    if response.status_code in {401, 402, 403}:
        return "authentication failed; verify LLM_API_KEY and provider settings"
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                detail = message.strip()
        elif isinstance(error, str) and error.strip():
            detail = error.strip()
        elif isinstance(payload.get("message"), str) and payload["message"].strip():
            detail = payload["message"].strip()
    if not detail:
        detail = response.text.strip()
    if not detail:
        return "no error detail"
    detail = detail[:400]
    if api_key:
        detail = detail.replace(api_key, "«redacted api key»")
    return _KEY_PATTERN.sub("«redacted api key»", detail)

"""Tests for the OpenAI-compatible model client and citation hygiene."""

from __future__ import annotations

import httpx
import pytest

from app.engine.copilot.llm import LLMClient, LLMError
from app.engine.copilot.answers import strip_unknown_citations

# Saved before the autouse fixture replaces the attribute, so the fake client can
# still build a real AsyncClient around an httpx.MockTransport.
_REAL_ASYNC_CLIENT = httpx.AsyncClient
_CURRENT: dict = {"handler": None}


class _FakeAsyncClient:
    """Drop-in replacement for ``httpx.AsyncClient`` backed by a mock transport."""

    def __init__(self, *args, **kwargs):
        handler = _CURRENT.get("handler")
        if handler is None:
            raise AssertionError("No mock transport was installed")
        kwargs["transport"] = httpx.MockTransport(handler)
        self._client = _REAL_ASYNC_CLIENT(*args, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self._client.aclose()

    async def post(self, *args, **kwargs):
        return await self._client.post(*args, **kwargs)


def client(handler, **overrides) -> LLMClient:
    _CURRENT["handler"] = handler
    return LLMClient(
        provider=overrides.get("provider", "openai-compatible"),
        api_key=overrides.get("api_key", "test-key"),
        base_url=overrides.get("base_url", "https://example.invalid/v1"),
        model=overrides.get("model", "test-model"),
        timeout_seconds=overrides.get("timeout_seconds", 2),
    )


@pytest.fixture(autouse=True)
def patch_async_client(monkeypatch):
    import app.engine.copilot.llm as module

    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    _CURRENT["handler"] = None
    yield
    _CURRENT["handler"] = None


async def run_complete(llm: LLMClient, messages=None):
    return await llm.complete(messages or [{"role": "user", "content": "hi"}])


class TestProviderStatus:
    def test_key_is_reported_but_never_exposed(self):
        llm = LLMClient(api_key="top-secret", provider="openai-compatible")
        status = llm.status()
        assert status["key_configured"] is True
        assert status["ai_enabled"] is True
        assert "top-secret" not in str(status)

    def test_local_provider_can_run_without_a_key(self):
        llm = LLMClient(provider="ollama", api_key="", base_url="http://localhost:11434/v1")
        assert llm.enabled is True
        assert llm.configured is False

    def test_disabled_provider(self):
        llm = LLMClient(provider="none", api_key="key")
        assert llm.enabled is False
        assert llm.status()["ai_enabled"] is False

    def test_endpoint_normalisation(self):
        assert LLMClient(base_url="https://x/v1")._endpoint() == "https://x/v1/chat/completions"
        assert (
            LLMClient(base_url="https://x/v1/chat/completions")._endpoint()
            == "https://x/v1/chat/completions"
        )


class TestComplete:
    @pytest.mark.asyncio
    async def test_successful_completion(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "  grounded answer  "}}]},
            )

        result = await run_complete(client(handler))
        assert result.content == "grounded answer"
        assert result.model == "test-model"
        assert seen["url"] == "https://example.invalid/v1/chat/completions"
        assert seen["authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_invalid_payload_is_a_safe_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        with pytest.raises(LLMError, match="invalid response payload"):
            await run_complete(client(handler))

    @pytest.mark.asyncio
    async def test_empty_content_is_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]})

        with pytest.raises(LLMError, match="empty response"):
            await run_complete(client(handler))

    @pytest.mark.asyncio
    async def test_auth_error_is_reported_without_credentials(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": {"message": "Incorrect API key provided: key_lb2t********2gLt"}},
            )

        llm = client(handler, api_key="test-key")
        with pytest.raises(LLMError) as excinfo:
            await run_complete(llm)
        message = str(excinfo.value)
        assert "HTTP 401" in message
        assert "authentication failed" in message
        assert "test-key" not in message
        assert "key_lb2t" not in message
        assert "********" not in message

    async def test_non_auth_error_redacts_key_like_fragments(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "bad request for sk-abcdef123456"}},
            )

        llm = client(handler, api_key="test-key")
        with pytest.raises(LLMError) as excinfo:
            await run_complete(llm)
        message = str(excinfo.value)
        assert "bad request" in message
        assert "sk-abcdef123456" not in message
        assert "«redacted api key»" in message

    @pytest.mark.asyncio
    async def test_unreachable_provider_is_a_safe_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(LLMError, match="Could not reach"):
            await run_complete(client(handler))

    @pytest.mark.asyncio
    async def test_disabled_client_does_not_call_the_provider(self):
        llm = LLMClient(provider="none", api_key="")
        with pytest.raises(LLMError, match="No language-model provider"):
            await run_complete(llm)


class TestCitationHygiene:
    def test_removes_only_unknown_ids(self):
        cleaned, warnings = strip_unknown_citations(
            "Fact [E1]. Another [E2]. Bogus [E99].", ["E1", "E2"]
        )
        assert "[E1]" in cleaned
        assert "[E2]" in cleaned
        assert "[E99]" not in cleaned
        assert any("E99" in warning for warning in warnings)

    def test_duplicate_unknown_ids_warn_once(self):
        cleaned, warnings = strip_unknown_citations("[E99] [E99]", ["E1"])
        assert cleaned == ""
        assert len(warnings) == 1

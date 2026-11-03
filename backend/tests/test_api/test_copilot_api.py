"""API tests for IMPACTMAP Copilot and its supporting endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import copilot as copilot_api
from app.core.database import Base, engine
from app.engine.copilot.llm import LLMError, LLMResult
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def scan(client: AsyncClient, path: Path) -> str:
    response = await client.post("/api/repositories/scan", json={"path": str(path)})
    assert response.status_code == 201, response.text
    return response.json()["repository"]["id"]


class FakeLLM:
    enabled = True

    async def complete(self, messages, *, temperature=0.15):
        return LLMResult(
            content="A model answer grounded in [E1], with a bogus [E999] citation.",
            model="fake-model",
            provider="fake",
        )


class FailingLLM:
    enabled = True

    async def complete(self, messages, *, temperature=0.15):
        raise LLMError("provider unavailable")


class TestCopilotStatus:
    @pytest.mark.asyncio
    async def test_status_never_returns_the_api_key(self, client, monkeypatch):
        monkeypatch.setattr(copilot_api._service.llm, "api_key", "sk-super-secret-value")

        response = await client.get("/api/copilot/status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["key_configured"] is True
        assert "sk-super-secret-value" not in response.text
        assert "api_key" not in payload
        assert payload["retrieval"]
        assert payload["setup"]


class TestCopilotChat:
    @pytest.mark.asyncio
    async def test_chat_returns_cited_offline_answer(self, client, sample_repo_copy: Path):
        repo_id = await scan(client, sample_repo_copy)

        response = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "Explain how the calculator works"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["conversation_id"].startswith("")
        assert payload["intent"] == "explain"
        assert payload["ai_enabled"] is False
        assert payload["evidence"]
        assert all(item["id"].startswith("E") for item in payload["evidence"])
        assert "local repository evidence" in payload["message"]["content"]
        assert "no language-model provider is configured" in payload["message"]["content"]
        assert payload["follow_ups"]
        assert payload["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_conversation_history_and_follow_up(self, client, git_repo: Path):
        repo_id = await scan(client, git_repo)

        first = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "What changed in Git?"},
        )
        assert first.status_code == 201, first.text
        conversation_id = first.json()["conversation_id"]

        second = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "Tell me more about that", "conversation_id": conversation_id},
        )
        assert second.status_code == 201, second.text
        assert second.json()["conversation_id"] == conversation_id
        assert second.json()["intent"] == "git"

        listed = await client.get(
            "/api/copilot/conversations", params={"repository_id": repo_id}
        )
        assert listed.status_code == 200
        summary = listed.json()["conversations"][0]
        assert summary["message_count"] == 4
        assert summary["title"] == "What changed in Git?"

        detail = await client.get(f"/api/copilot/conversations/{conversation_id}")
        assert detail.status_code == 200
        messages = detail.json()["messages"]
        assert [message["role"] for message in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert messages[0]["evidence"] == []
        assert messages[1]["evidence"]

    @pytest.mark.asyncio
    async def test_conversation_cannot_cross_repositories(
        self, client, sample_repo_copy: Path, tmp_path: Path
    ):
        first_repo = await scan(client, sample_repo_copy)
        other = tmp_path / "other"
        other.mkdir()
        (other / "app.py").write_text("def main():\n    return 1\n")
        second_repo = await scan(client, other)

        response = await client.post(
            f"/api/copilot/repositories/{first_repo}/chat",
            json={"message": "Explain the calculator"},
        )
        conversation_id = response.json()["conversation_id"]

        mismatch = await client.post(
            f"/api/copilot/repositories/{second_repo}/chat",
            json={"message": "Continue", "conversation_id": conversation_id},
        )
        assert mismatch.status_code == 400
        assert "different repository" in mismatch.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_repository_and_conversation(self, client):
        response = await client.post(
            "/api/copilot/repositories/missing/chat", json={"message": "hello"}
        )
        assert response.status_code == 404

        response = await client.get("/api/copilot/conversations/missing")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_blank_message_is_rejected(self, client, sample_repo_copy: Path):
        repo_id = await scan(client, sample_repo_copy)
        response = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat", json={"message": "   "}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_conversation(self, client, sample_repo_copy: Path):
        repo_id = await scan(client, sample_repo_copy)
        response = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "Explain the calculator"},
        )
        conversation_id = response.json()["conversation_id"]

        deleted = await client.delete(f"/api/copilot/conversations/{conversation_id}")
        assert deleted.status_code == 204
        gone = await client.get(f"/api/copilot/conversations/{conversation_id}")
        assert gone.status_code == 404


class TestModelIntegration:
    @pytest.mark.asyncio
    async def test_model_answer_is_used_and_unknown_citations_removed(
        self, client, sample_repo_copy: Path, monkeypatch
    ):
        monkeypatch.setattr(copilot_api._service, "llm", FakeLLM())
        repo_id = await scan(client, sample_repo_copy)

        response = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "Explain the calculator"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["ai_enabled"] is True
        assert payload["model"] == "fake-model"
        assert "[E999]" not in payload["message"]["content"]
        assert any("E999" in warning for warning in payload["warnings"])

    @pytest.mark.asyncio
    async def test_provider_failure_falls_back_to_local_evidence(
        self, client, sample_repo_copy: Path, monkeypatch
    ):
        monkeypatch.setattr(copilot_api._service, "llm", FailingLLM())
        repo_id = await scan(client, sample_repo_copy)

        response = await client.post(
            f"/api/copilot/repositories/{repo_id}/chat",
            json={"message": "Explain the calculator"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["ai_enabled"] is False
        assert payload["model"] is None
        assert any("model provider call failed" in warning for warning in payload["warnings"])
        content = payload["message"]["content"]
        assert "local repository evidence" in content
        assert "because the model-provider call failed" in content
        assert "no language-model provider is configured" not in content


class TestRepositorySupportEndpoints:
    @pytest.mark.asyncio
    async def test_git_refs_for_one_commit_repository(self, client, git_repo: Path):
        repo_id = await scan(client, git_repo)
        response = await client.get(f"/api/repositories/{repo_id}/git-refs")
        assert response.status_code == 200
        payload = response.json()
        assert payload["is_repository"] is True
        assert payload["commit_count"] == 1
        assert payload["recommended_base"] == "HEAD"
        assert payload["recommended_head"] == "WORKING"
        assert payload["warnings"]

    @pytest.mark.asyncio
    async def test_git_refs_for_zero_commit_repository(self, client, tmp_path: Path):
        from tests.conftest import git

        repo = tmp_path / "empty-history"
        repo.mkdir()
        (repo / "app.py").write_text("def run():\n    return 1\n")
        assert git(repo, "init", "-q").returncode == 0

        repo_id = await scan(client, repo)
        response = await client.get(f"/api/repositories/{repo_id}/git-refs")
        assert response.status_code == 200
        payload = response.json()
        assert payload["is_repository"] is True
        assert payload["commit_count"] == 0
        assert payload["recommended_base"] == "EMPTY"
        assert payload["recommended_head"] == "WORKING"

    @pytest.mark.asyncio
    async def test_file_viewer_is_read_only_and_path_validated(
        self, client, sample_repo_copy: Path
    ):
        repo_id = await scan(client, sample_repo_copy)

        response = await client.get(
            f"/api/repositories/{repo_id}/file",
            params={"path": "calculator.py", "start_line": 1, "end_line": 5},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["path"] == "calculator.py"
        assert payload["line_count"] >= 5
        assert payload["start_line"] == 1
        assert payload["end_line"] == 5
        assert payload["language"] == "python"

        traversal = await client.get(
            f"/api/repositories/{repo_id}/file", params={"path": "../outside.py"}
        )
        assert traversal.status_code == 400

        absolute = await client.get(
            f"/api/repositories/{repo_id}/file", params={"path": "/etc/passwd"}
        )
        assert absolute.status_code == 400

        missing = await client.get(
            f"/api/repositories/{repo_id}/file", params={"path": "missing.py"}
        )
        assert missing.status_code == 400

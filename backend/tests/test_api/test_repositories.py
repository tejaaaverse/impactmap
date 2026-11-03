"""
Tests for the repository API endpoints.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile
import os

from app.main import app
from app.core.database import init_db, engine, Base


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create fresh database tables for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_repo(tmp_path):
    """Create a temporary repository."""
    (tmp_path / "main.py").write_text("def hello():\n    print('hi')\n")
    (tmp_path / "helpers.py").write_text(
        "import os\n\nclass Helper:\n    def run(self):\n        pass\n"
    )
    return tmp_path


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_scan_repository(client, sample_repo):
    response = await client.post(
        "/api/repositories/scan",
        json={"path": str(sample_repo)},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["files_discovered"] == 2
    assert data["functions_discovered"] == 1  # hello()
    assert data["classes_discovered"] == 1  # Helper
    assert data["scan_duration_ms"] > 0
    assert data["repository"]["status"] == "scanned"


@pytest.mark.asyncio
async def test_scan_invalid_path(client):
    response = await client.post(
        "/api/repositories/scan",
        json={"path": "/nonexistent/path"},
    )
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_list_repositories(client, sample_repo):
    # First, scan a repo
    await client.post("/api/repositories/scan", json={"path": str(sample_repo)})

    response = await client.get("/api/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == sample_repo.name


@pytest.mark.asyncio
async def test_get_repository_detail(client, sample_repo):
    # Scan
    scan_resp = await client.post(
        "/api/repositories/scan", json={"path": str(sample_repo)}
    )
    repo_id = scan_resp.json()["repository"]["id"]

    # Get detail
    response = await client.get(f"/api/repositories/{repo_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == repo_id
    assert len(data["entities"]) > 0


@pytest.mark.asyncio
async def test_get_nonexistent_repository(client):
    response = await client.get("/api/repositories/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rescan_repository(client, sample_repo):
    # Scan once
    resp1 = await client.post(
        "/api/repositories/scan", json={"path": str(sample_repo)}
    )
    assert resp1.status_code == 201

    # Add a file and rescan
    (sample_repo / "new_module.py").write_text("def new_func():\n    pass\n")
    resp2 = await client.post(
        "/api/repositories/scan", json={"path": str(sample_repo)}
    )
    assert resp2.status_code == 201
    assert resp2.json()["files_discovered"] == 3

    # Should still be only one repo
    repos = await client.get("/api/repositories")
    assert len(repos.json()) == 1

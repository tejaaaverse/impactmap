"""End-to-end API tests for analysis, graph, coverage and execution."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, engine
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


async def scan(client: AsyncClient, repo: Path) -> str:
    response = await client.post("/api/repositories/scan", json={"path": str(repo)})
    assert response.status_code == 201, response.text
    return response.json()["repository"]["id"]


async def analyze(client: AsyncClient, repo_id: str, base_ref="HEAD", head_ref="WORKING"):
    response = await client.post(
        f"/api/repositories/{repo_id}/analyze",
        json={"base_ref": base_ref, "head_ref": head_ref},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_full_analysis_workflow(client, git_repo: Path):
    helper = git_repo / "utils" / "math_helpers.py"
    helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))

    repo_id = await scan(client, git_repo)
    detail = await client.get(f"/api/repositories/{repo_id}")
    assert detail.status_code == 200
    assert detail.json()["is_git_repository"] is True
    assert detail.json()["entities"]

    graph = await client.get(f"/api/repositories/{repo_id}/graph")
    assert graph.status_code == 200
    assert graph.json()["stats"]["nodes"] > 20
    assert any(node["type"] == "class" for node in graph.json()["nodes"])

    result = await analyze(client, repo_id)
    analysis = result["analysis"]
    assert analysis["status"] == "completed"
    assert analysis["total_changed_files"] == 1
    assert analysis["total_affected_entities"] >= 2
    assert analysis["impact"]["direct_impacts"]
    assert analysis["selection"]["coverage_available"] is False
    assert analysis["selection"]["safe"]["fallback_used"] is True

    analysis_id = analysis["id"]
    impact = await client.get(f"/api/analysis/{analysis_id}/impact")
    assert impact.status_code == 200
    names = {
        item["qualified_name"]
        for item in impact.json()["direct_impacts"] + impact.json()["indirect_impacts"]
    }
    assert "utils.math_helpers.add" in names

    tests = await client.get(f"/api/analysis/{analysis_id}/tests")
    assert tests.status_code == 200
    assert tests.json()["optimized"]["selected_tests"]

    listing = await client.get("/api/analysis")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_analysis_requires_git_repository(client, sample_repo_copy: Path):
    repo_id = await scan(client, sample_repo_copy)
    response = await client.post(
        f"/api/repositories/{repo_id}/analyze",
        json={"base_ref": "HEAD", "head_ref": "WORKING"},
    )
    assert response.status_code == 400
    assert "Git" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_analysis_and_repository_return_404(client):
    assert (await client.get("/api/analysis/nope")).status_code == 404
    assert (await client.get("/api/analysis/nope/impact")).status_code == 404
    assert (await client.get("/api/analysis/nope/tests")).status_code == 404
    assert (await client.get("/api/repositories/nope/graph")).status_code == 404


@pytest.mark.asyncio
async def test_test_execution_requires_confirmation(client, git_repo: Path):
    helper = git_repo / "utils" / "math_helpers.py"
    helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))
    repo_id = await scan(client, git_repo)
    analysis = await analyze(client, repo_id)
    analysis_id = analysis["analysis"]["id"]

    response = await client.post(
        f"/api/analysis/{analysis_id}/run-tests",
        json={"mode": "optimized", "confirm": False},
    )
    assert response.status_code == 400
    assert "confirm" in response.json()["detail"].lower()

    response = await client.post(
        f"/api/analysis/{analysis_id}/run-tests",
        json={"mode": "optimized", "confirm": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["passed"] >= 1
    assert body["failed"] == 0
    assert body["mode"] == "optimized"

    history = await client.get(f"/api/analysis/{analysis_id}/test-runs")
    assert history.status_code == 200
    assert history.json()["total"] == 1


@pytest.mark.asyncio
async def test_coverage_endpoint_enables_coverage_selection(client, git_repo: Path):
    helper = git_repo / "utils" / "math_helpers.py"
    helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))
    repo_id = await scan(client, git_repo)

    denied = await client.post(
        f"/api/repositories/{repo_id}/coverage", json={"confirm": False}
    )
    assert denied.status_code == 400

    collected = await client.post(
        f"/api/repositories/{repo_id}/coverage",
        json={"confirm": True, "timeout_seconds": 120},
    )
    assert collected.status_code == 201, collected.text
    body = collected.json()
    assert body["snapshot"]["status"] == "completed"
    assert body["snapshot"]["measured_tests"] == 20
    assert body["execution"]["passed"] == 20

    snapshots = await client.get(f"/api/repositories/{repo_id}/coverage")
    assert snapshots.status_code == 200
    assert len(snapshots.json()) == 1

    result = await analyze(client, repo_id)
    selection = result["analysis"]["selection"]
    assert selection["coverage_available"] is True
    assert selection["measured_tests"] == 20
    assert selection["optimized"]["selected_count"] < 20


@pytest.mark.asyncio
async def test_benchmark_runs_both_suites_and_dashboard_is_real(client, git_repo: Path):
    helper = git_repo / "utils" / "math_helpers.py"
    helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))
    repo_id = await scan(client, git_repo)
    analysis = await analyze(client, repo_id)
    analysis_id = analysis["analysis"]["id"]

    unconfirmed = await client.post(
        "/api/benchmarks/run",
        json={
            "repository_id": repo_id,
            "analysis_id": analysis_id,
            "mode": "optimized",
            "confirm": False,
        },
    )
    assert unconfirmed.status_code == 400

    response = await client.post(
        "/api/benchmarks/run",
        json={
            "repository_id": repo_id,
            "analysis_id": analysis_id,
            "mode": "optimized",
            "dataset_name": "calculator-working-tree",
            "confirm": True,
            "timeout_seconds": 120,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_run"]["passed"] == 20
    assert body["selected_run"]["total_tests"] >= 1
    assert body["full_duration_ms"] > 0
    assert body["reduction_percent"] is not None
    assert body["metrics"]["precision_recall_definition"]

    listing = await client.get("/api/benchmarks")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    dashboard = await client.get("/api/dashboard")
    assert dashboard.status_code == 200
    stats = dashboard.json()
    assert stats["repositories"] == 1
    assert stats["analyses"] == 1
    assert stats["benchmark_runs"] == 1
    assert stats["average_analysis_ms"] is not None
    assert stats["recent_benchmarks"]


@pytest.mark.asyncio
async def test_scan_rejects_system_directory(client):
    response = await client.post("/api/repositories/scan", json={"path": "/etc"})
    assert response.status_code in (400, 422)

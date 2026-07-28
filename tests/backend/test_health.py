"""Tests for GET /health (docs/API_CONTRACT.md §7)."""

from httpx import AsyncClient


async def test_health_reports_db_and_cache_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"] is True
    assert body["cache"] is True
    assert body["status"] in {"ok", "degraded"}


async def test_health_does_not_require_api_key(client: AsyncClient) -> None:
    # No X-API-Key header sent — health must stay reachable for
    # docker-compose healthchecks (see app/api/deps.py:verify_api_key).
    response = await client.get("/api/v1/health")
    assert response.status_code == 200

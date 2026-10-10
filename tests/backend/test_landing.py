"""The public home page at / (no login, no API key)."""

from httpx import AsyncClient

from app.core.config import get_settings


async def test_home_page_is_public_and_describes_the_product(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Understand any lecture slide" in html
    assert 'href="/privacy"' in html  # the policy Google and the Web Store link to


async def test_home_page_quotes_the_real_limits_and_retention(client: AsyncClient) -> None:
    settings = get_settings()
    html = (await client.get("/")).text
    assert f"{settings.rate_limit_captures_per_day} captures a day" in html
    assert f"{settings.rate_limit_captures_per_month} a month" in html
    assert f"kept {settings.chat_retention_days} days" in html
    assert "__" not in html  # no unfilled placeholder left behind


async def test_home_page_never_contains_a_secret(client: AsyncClient) -> None:
    html = (await client.get("/")).text
    settings = get_settings()
    for secret in (settings.local_api_key, settings.anthropic_api_key, settings.database_url):
        if secret:
            assert secret not in html
    assert "<script" not in html  # no scripts or trackers


async def test_the_api_still_answers_under_its_prefix(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).status_code == 200

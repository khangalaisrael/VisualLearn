"""The public home page (/) and the install guide (/install): no login, no API key."""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings


@pytest.fixture
def download_url():
    """Set EXTENSION_DOWNLOAD_URL for a test and always put it back."""
    settings = get_settings()
    original = settings.extension_download_url

    def _set(value: str | None) -> None:
        settings.extension_download_url = value

    yield _set
    settings.extension_download_url = original


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
    assert f"Without signing in you get {settings.rate_limit_anonymous_captures_per_day} a day" in html
    assert "__" not in html  # no unfilled placeholder left behind


async def test_pages_never_contain_a_secret_or_a_script(client: AsyncClient) -> None:
    settings = get_settings()
    for path in ("/", "/install"):
        html = (await client.get(path)).text
        for secret in (settings.local_api_key, settings.anthropic_api_key, settings.database_url):
            if secret:
                assert secret not in html
        assert "<script" not in html


async def test_the_api_still_answers_under_its_prefix(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).status_code == 200


# --- without a download link: ask for early access -------------------------------------


async def test_without_a_download_link_people_are_asked_to_email(client: AsyncClient, download_url) -> None:
    download_url(None)
    home = (await client.get("/")).text
    assert "Get early access" in home
    assert "mailto:" in home
    install = (await client.get("/install")).text
    assert "isn't public yet" in install
    assert "Download the extension" not in install
    assert "__" not in install


# --- with a download link ----------------------------------------------------------------


async def test_with_a_download_link_the_install_page_offers_it(client: AsyncClient, download_url) -> None:
    download_url("https://github.com/khangalaisrael/VisualLearn/releases/download/v0.1.0/VisionLearn-extension.zip")
    install = (await client.get("/install")).text
    assert 'href="https://github.com/khangalaisrael/VisualLearn/releases/download/v0.1.0/VisionLearn-extension.zip"' in install
    assert "Download the extension" in install
    assert "Load unpacked" in install and "Developer mode" in install  # the steps are all there
    assert "__" not in install

    home = (await client.get("/")).text
    assert "Add it to Chrome" in home
    assert 'href="/install"' in home
    assert "Get early access" not in home


@pytest.mark.parametrize(
    "bad",
    ["javascript:alert(1)", "http://insecure.example/x.zip", "data:text/html,hi", "//evil.example/x.zip", "   "],
)
async def test_only_a_plain_https_link_is_ever_shown(client: AsyncClient, download_url, bad: str) -> None:
    download_url(bad)
    install = (await client.get("/install")).text
    assert "Download the extension" not in install
    assert bad.strip() not in install or not bad.strip()
    assert "isn't public yet" in install


async def test_a_link_cannot_break_out_of_its_attribute(client: AsyncClient, download_url) -> None:
    download_url('https://example.com/x.zip"><script>alert(1)</script>')
    install = (await client.get("/install")).text
    assert "<script" not in install
    assert "&quot;" in install

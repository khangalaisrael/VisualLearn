"""app/db/url.py — hosted-provider DATABASE_URLs become asyncpg URLs."""

from app.db.url import normalize_database_url


def test_neon_style_url_is_converted_for_asyncpg() -> None:
    url, connect_args = normalize_database_url(
        "postgresql://alex:p%40ss@ep-cool-1234.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://alex:p%40ss@ep-cool-1234.eu-central-1.aws.neon.tech/neondb"
    assert connect_args == {"ssl": True}


def test_postgres_scheme_alias_is_accepted() -> None:
    url, _ = normalize_database_url("postgres://u:p@host:5432/db")
    assert url == "postgresql+asyncpg://u:p@host:5432/db"


def test_local_asyncpg_url_is_unchanged() -> None:
    local = "postgresql+asyncpg://visionlearn:visionlearn@db:5432/visionlearn"
    assert normalize_database_url(local) == (local, {})


def test_unrelated_query_params_are_kept() -> None:
    url, connect_args = normalize_database_url("postgresql://u:p@h/db?sslmode=disable&application_name=vl")
    assert url == "postgresql+asyncpg://u:p@h/db?application_name=vl"
    assert connect_args == {}

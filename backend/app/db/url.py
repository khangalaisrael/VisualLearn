"""DATABASE_URL normalization for hosted Postgres providers.

Hosted providers (Neon, Supabase, Render, ...) hand out libpq-style URLs —
`postgresql://user:pass@host/db?sslmode=require&channel_binding=require` —
but the app talks to Postgres through SQLAlchemy's asyncpg dialect, which
needs the `postgresql+asyncpg://` scheme and rejects libpq-only query
parameters like `sslmode` (asyncpg takes `ssl` as a connect argument
instead). This turns a pasted provider URL into what the engine expects,
so the URL can be copied from the provider's dashboard unchanged.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# libpq parameters asyncpg doesn't understand. `sslmode` is translated into
# an `ssl` connect argument; the rest are dropped (asyncpg negotiates
# SCRAM/channel binding on its own).
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey", "target_session_attrs"}
_SSL_REQUIRED_MODES = {"require", "verify-ca", "verify-full"}


def normalize_database_url(url: str) -> tuple[str, dict]:
    """Returns `(asyncpg_url, connect_args)` for `create_async_engine`."""
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    query = parse_qsl(parts.query, keep_blank_values=True)
    sslmode = next((value for key, value in query if key == "sslmode"), None)
    kept = [(key, value) for key, value in query if key not in _LIBPQ_ONLY_PARAMS]

    connect_args: dict = {}
    if sslmode in _SSL_REQUIRED_MODES:
        connect_args["ssl"] = True

    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)), connect_args

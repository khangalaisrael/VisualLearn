"""Running a student's Haskell or Java program (services/code_runner.py, api/v1/code.py).

No test reaches the real sandbox: the endpoint tests use the placeholder
runner from conftest, and the Wandbox client is given a fake transport.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_code_runner
from app.core.config import get_settings
from app.main import app
from app.models.orm import Session as SessionRow
from app.models.orm import User
from app.services.code_runner import (
    MAX_OUTPUT_CHARS,
    CodeRunnerUnavailable,
    WandboxCodeRunner,
    parse_result,
    prepare_source,
)

API_KEY = {"X-API-Key": "test-api-key"}
URL = "/api/v1/code/run"


async def _sign_in(db_session: AsyncSession, email: str) -> dict[str, str]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db_session.add(user)
    await db_session.flush()
    token = f"token-{email}"
    db_session.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=token, expires_at=datetime.now(UTC) + timedelta(days=1)))
    await db_session.commit()
    return {**API_KEY, "Authorization": f"Bearer {token}"}


@pytest.fixture
def run_limit():
    settings = get_settings()
    original = (settings.rate_limit_code_runs_per_day, settings.admin_emails)
    settings.admin_emails = ""
    yield settings
    settings.rate_limit_code_runs_per_day, settings.admin_emails = original


# --- the endpoint ---------------------------------------------------------------------


async def test_a_signed_in_user_runs_a_program(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    response = await client.post(URL, json={"language": "haskell", "code": "main = interact id", "stdin": "hi"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "stdout": "haskell:hi", "stderr": "", "compiler_output": "", "duration_ms": 1}


async def test_running_code_needs_an_account_a_known_language_and_some_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    assert (await client.post(URL, json={"language": "java", "code": "class A {}"}, headers=API_KEY)).status_code == 401
    headers = await _sign_in(db_session, "a@example.com")
    assert (await client.post(URL, json={"language": "python", "code": "print(1)"}, headers=headers)).status_code == 422
    assert (await client.post(URL, json={"language": "java", "code": "   "}, headers=headers)).status_code == 422
    assert (await client.post(URL, json={"language": "java", "code": "x" * 20_001}, headers=headers)).status_code == 422


async def test_the_daily_allowance_for_runs(client: AsyncClient, db_session: AsyncSession, run_limit) -> None:
    run_limit.rate_limit_code_runs_per_day = 2
    headers = await _sign_in(db_session, "a@example.com")
    body = {"language": "java", "code": "class A {}"}
    assert [(await client.post(URL, json=body, headers=headers)).status_code for _ in range(3)] == [200, 200, 429]
    other = await _sign_in(db_session, "b@example.com")
    assert (await client.post(URL, json=body, headers=other)).status_code == 200  # counted per person


async def test_an_unreachable_sandbox_is_reported_plainly(client: AsyncClient, db_session: AsyncSession) -> None:
    class _Down:
        async def run(self, language, code, stdin):
            raise CodeRunnerUnavailable("connection refused")

    app.dependency_overrides[get_code_runner] = lambda: _Down()
    headers = await _sign_in(db_session, "a@example.com")
    response = await client.post(URL, json={"language": "java", "code": "class A {}"}, headers=headers)
    assert response.status_code == 503
    assert "not answering" in response.json()["detail"]


# --- what is sent to the sandbox, and how its answer is read ------------------------------


def test_java_public_types_are_sent_without_public() -> None:
    source = "import java.util.*;\npublic class Main {\n  public static void main(String[] a) {}\n}\npublic final class B {}\n  public interface C {}"
    sent = prepare_source("java", source)
    assert "\nclass Main {" in sent and "\nfinal class B {}" in sent and "\n  interface C {}" in sent
    assert "public static void main" in sent  # members keep their modifiers
    assert prepare_source("haskell", "public class X") == "public class X"


def _payload(**fields) -> dict:
    return {"status": "0", "signal": "", "compiler_error": "", "program_output": "", "program_error": "", **fields}


def test_reading_the_sandbox_answer() -> None:
    ok = parse_result("haskell", _payload(compiler_error="[1 of 2] Compiling Main ( prog.hs, prog.o )\n[2 of 2] Linking prog.exe\n", program_output="55\n"), 12)
    assert (ok.status, ok.stdout, ok.compiler_output, ok.duration_ms) == ("ok", "55\n", "", 12)

    broken = parse_result("haskell", _payload(status="1", compiler_error="[1 of 2] Compiling Main ( prog.hs, prog.o )\nprog.hs:1:22: error: no\n"), 1)
    assert (broken.status, broken.compiler_output) == ("compile_error", "prog.hs:1:22: error: no")

    crashed = parse_result("java", _payload(status="1", program_error="Exception in thread main"), 1)
    assert (crashed.status, crashed.stderr) == ("runtime_error", "Exception in thread main")

    assert parse_result("haskell", _payload(status="137"), 1).status == "timeout"
    assert parse_result("java", _payload(status="1", signal="Killed"), 1).status == "timeout"

    # A warning with a successful run is still a success, and the warning is kept.
    warned = parse_result("java", _payload(compiler_error="Note: prog.java uses unchecked operations.", program_output="1"), 1)
    assert (warned.status, warned.compiler_output) == ("ok", "Note: prog.java uses unchecked operations.")

    long = parse_result("java", _payload(program_output="x" * (MAX_OUTPUT_CHARS + 50)), 1)
    assert len(long.stdout) < MAX_OUTPUT_CHARS + 40 and long.stdout.endswith("(output cut off here)")


async def test_the_wandbox_client_posts_the_program_and_reads_the_answer() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_payload(program_output="42\n"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as fake:
        result = await WandboxCodeRunner("https://sandbox.test/run", 5, client=fake).run("java", "public class Main {}", "21")
    assert seen == {"compiler": "openjdk-jdk-22+36", "code": "class Main {}", "stdin": "21"}
    assert (result.status, result.stdout) == ("ok", "42\n")


async def test_the_wandbox_client_reports_failures_as_unavailable() -> None:
    for response in (httpx.Response(503, text="busy"), httpx.Response(200, text="<html>"), httpx.Response(200, json=["nope"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request, r=response: r)) as fake:
            with pytest.raises(CodeRunnerUnavailable):
                await WandboxCodeRunner("https://sandbox.test/run", 5, client=fake).run("haskell", "main = pure ()", "")

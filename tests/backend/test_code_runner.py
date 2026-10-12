"""Running a student's Haskell or Java program (services/code_runner.py, api/v1/code.py).

No test reaches the real sandbox: the endpoint tests use the placeholder
runner from conftest, and the Wandbox client is given a fake transport.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_code_fixer, get_code_runner
from app.core.config import get_settings
from app.main import app
from app.models.orm import Session as SessionRow
from app.models.orm import UsageEvent, User
from app.services.code_fixer import MAX_ERROR_CHARS, ClaudeCodeFixer, FixedCode, format_request, parse_fix
from app.services.code_tryout import MAX_EXPRESSIONS, with_expressions
from app.services.code_runner import (
    MAX_OUTPUT_CHARS,
    RunResult,
    CodeRunnerBusy,
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
    assert (await client.post(URL, json={"language": "ruby", "code": "puts 1"}, headers=headers)).status_code == 422
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


# --- C++ and Python -----------------------------------------------------------------------


async def test_every_language_is_accepted(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    for language in ("haskell", "java", "cpp", "python"):
        response = await client.post(URL, json={"language": language, "code": "x", "stdin": "1"}, headers=headers)
        assert response.status_code == 200 and response.json()["stdout"] == f"{language}:1"


async def test_cpp_is_compiled_as_cpp20_and_python_takes_no_options() -> None:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=_payload(program_output="1"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as fake:
        runner = WandboxCodeRunner("https://sandbox.test/run", 5, client=fake)
        await runner.run("cpp", "int main() {}", "")
        await runner.run("python", "print(1)", "")
    assert sent[0] == {"compiler": "gcc-13.2.0", "code": "int main() {}", "stdin": "", "compiler-option-raw": "-std=c++20"}
    assert sent[1] == {"compiler": "cpython-3.13.8", "code": "print(1)", "stdin": ""}
    assert prepare_source("cpp", "public class X") == "public class X"  # only Java loses `public`


# --- making code runnable -------------------------------------------------------------------

FIX_URL = "/api/v1/code/make-runnable"


async def test_code_is_made_runnable_and_the_call_is_recorded(client: AsyncClient, db_session: AsyncSession) -> None:
    class _Fixer:
        model_name = "claude-haiku-5-5"

        def __init__(self) -> None:
            self.seen: tuple | None = None

        async def make_runnable(self, language, code, stdin, last_run):
            self.seen = (language, code, stdin, last_run)
            return FixedCode(code="main = print (double 21)\n", note="Added a main.")

    fixer = _Fixer()
    app.dependency_overrides[get_code_fixer] = lambda: fixer
    headers = await _sign_in(db_session, "a@example.com")
    body = {"language": "haskell", "code": "double x = x + x", "stdin": "", "last_run": "no main"}
    response = await client.post(FIX_URL, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"code": "main = print (double 21)\n", "note": "Added a main."}
    assert fixer.seen == ("haskell", "double x = x + x", "", "no main")
    assert (await db_session.execute(select(UsageEvent.action))).scalars().all() == ["code_fix"]


async def test_making_code_runnable_needs_an_account_and_code_and_counts_as_chat(
    client: AsyncClient, db_session: AsyncSession, run_limit
) -> None:
    body = {"language": "java", "code": "int f() { return 1; }"}
    assert (await client.post(FIX_URL, json=body, headers=API_KEY)).status_code == 401
    headers = await _sign_in(db_session, "a@example.com")
    assert (await client.post(FIX_URL, json={**body, "code": " "}, headers=headers)).status_code == 422

    # A request counts when it is made, so the allowance is checked with a fresh account.
    other = await _sign_in(db_session, "b@example.com")
    original = run_limit.rate_limit_chat_messages_per_day
    run_limit.rate_limit_chat_messages_per_day = 1
    try:
        assert [(await client.post(FIX_URL, json=body, headers=other)).status_code for _ in range(2)] == [200, 429]
    finally:
        run_limit.rate_limit_chat_messages_per_day = original


async def test_a_fixer_that_fails_is_reported_plainly(client: AsyncClient, db_session: AsyncSession) -> None:
    class _Broken:
        model_name = "x"

        async def make_runnable(self, language, code, stdin, last_run):
            raise ValueError("no code")

    app.dependency_overrides[get_code_fixer] = lambda: _Broken()
    headers = await _sign_in(db_session, "a@example.com")
    response = await client.post(FIX_URL, json={"language": "python", "code": "def f(:"}, headers=headers)
    assert response.status_code == 502 and "could not be completed" in response.json()["detail"]


def test_the_fix_request_and_answer() -> None:
    plain = format_request("cpp", "int f();", "", "")
    assert plain == "Language: C++\n\n<code>\nint f();\n</code>"
    full = format_request("python", "print(x)", "3", "NameError" + "!" * (MAX_ERROR_CHARS + 10))
    assert "<input_the_program_reads>\n3\n" in full and full.count("!") == MAX_ERROR_CHARS - len("NameError")

    assert parse_fix({"code": "\nprint(1)\n\n", "note": "  Added   a call. "}) == FixedCode("print(1)\n", "Added a call.")
    for bad in ({"code": "  ", "note": "x"}, {"code": "x" * 20_001, "note": "x"}):
        with pytest.raises(ValueError):
            parse_fix(bad)


async def test_the_claude_fixer_sends_the_prompt_and_reads_json() -> None:
    fake = AsyncMock()
    fake.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps({"code": "print(1)", "note": "ok"}))], stop_reason="end_turn"
    )
    fixed = await ClaudeCodeFixer(client=fake, model="claude-haiku-5-5").make_runnable("python", "print(1", "", "SyntaxError")
    assert fixed == FixedCode("print(1)\n", "ok")
    call = fake.messages.create.call_args.kwargs
    assert call["system"].startswith("You turn a student's code into a complete program")
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "Language: Python" in call["messages"][0]["content"] and "<last_run>\nSyntaxError" in call["messages"][0]["content"]

    fake.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"code": "pri')], stop_reason="max_tokens")
    with pytest.raises(ValueError, match="ran out of room"):
        await ClaudeCodeFixer(client=fake, model="claude-haiku-5-5").make_runnable("python", "x", "", "")


# --- a sandbox that is turning requests away ----------------------------------------------------


async def test_a_busy_sandbox_is_asked_again_and_then_reported_as_busy(client: AsyncClient, db_session: AsyncSession) -> None:
    answers = [httpx.Response(429, text="slow down"), httpx.Response(200, json=_payload(program_output="7"))]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return answers[min(calls, len(answers)) - 1]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as fake:
        result = await WandboxCodeRunner("https://sandbox.test/run", 5, client=fake, retry_delays=(0, 0)).run("python", "print(7)", "")
    assert (result.stdout, calls) == ("7", 2)  # refused once, then served

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as fake:
        with pytest.raises(CodeRunnerBusy):
            await WandboxCodeRunner("https://sandbox.test/run", 5, client=fake, retry_delays=(0, 0)).run("python", "print(7)", "")

    class _Busy:
        async def run(self, language, code, stdin):
            raise CodeRunnerBusy("busy")

    app.dependency_overrides[get_code_runner] = lambda: _Busy()
    headers = await _sign_in(db_session, "a@example.com")
    response = await client.post(URL, json={"language": "python", "code": "print(7)"}, headers=headers)
    assert response.status_code == 503 and "busy right now" in response.json()["detail"]


# --- trying expressions, as in GHCi or the Python shell ---------------------------------------

_PRIMES = "isPrime :: Int -> Bool\nisPrime x = not $ any (\\d -> x `mod` d == 0) [2..(x - 1)]\n"


def test_haskell_expressions_become_the_missing_main() -> None:
    assert with_expressions("haskell", _PRIMES, "  \n") == _PRIMES  # nothing to try: untouched
    source = with_expressions("haskell", _PRIMES, "ghci> isPrime 10\n\nisPrime 13\n")
    assert source.startswith(_PRIMES.rstrip("\n"))
    assert source.endswith(
        "\n\nmain :: IO ()\nmain = do\n"
        '  putStrLn "ghci> isPrime 10"\n  print (isPrime 10)\n'
        '  putStrLn "ghci> isPrime 13"\n  print (isPrime 13)\n'
    )


def test_haskell_prompts_commands_statements_and_actions() -> None:
    tried = "\n".join(
        [
            "Prelude> :load primeSearch.hs",
            "load primeSearch.hs",
            "*Main> let n = 7",
            "λ> putStrLn \"hi\"",
            'show "a\\b"',
            ":t isPrime",
        ]
    )
    main = with_expressions("haskell", _PRIMES, tried).split("main = do\n")[1]
    assert main.count("(not needed here: your code is already loaded)") == 2  # the two loads
    assert main.count("(GHCi commands are not available here, only expressions)") == 1  # :t
    assert "  let n = 7\n" in main and '  putStrLn "hi"\n' in main
    assert '  putStrLn "ghci> show \\"a\\\\b\\""\n  print (show "a\\b")\n' in main
    assert "print (:" not in main and "print (load" not in main and "print (let" not in main


def test_haskell_code_that_has_its_own_main_keeps_it_under_another_name() -> None:
    code = "module Main where\n\nmain :: IO ()\nmain = putStrLn \"mine\"\n\nremain = 1\n"
    source = with_expressions("haskell", code, "import Data.List (sort)\nmain\nsort [3, 1, 2]")
    assert source.startswith("module Main where\nimport Data.List (sort)\n")
    assert 'studentMain :: IO ()\nstudentMain = putStrLn "mine"' in source and "remain = 1" in source
    assert source.count("\nmain :: IO ()") == 1
    assert '  putStrLn "ghci> main"\n  studentMain\n' in source and "  print (sort [3, 1, 2])\n" in source
    # Without a module header the import goes first.
    assert with_expressions("haskell", "x = 1\n", "import Data.Char\nx").startswith("import Data.Char\nx = 1")


def test_python_expressions_are_evaluated_after_the_code() -> None:
    source = with_expressions("python", "def twice(n):\n    return n * 2\n", ">>> twice(21)\nx = 3\n... \n'é'")
    assert source.startswith("def twice(n):\n    return n * 2\n\n\ndef _try_expressions(".replace("\n\n\ndef", "\n\ndef"))
    assert source.rstrip().endswith('_try_expressions(["twice(21)", "x = 3", "\'\\u00e9\'"])')
    # The generated program really behaves like the shell.
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(source, "<test>", "exec"), {"__name__": "__main__"})
    assert out.getvalue() == ">>> twice(21)\n42\n>>> x = 3\n>>> 'é'\n'é'\n"


def test_expressions_are_capped_and_only_for_languages_with_a_prompt() -> None:
    many = with_expressions("haskell", "x = 1\n", "\n".join(["x"] * (MAX_EXPRESSIONS + 5)))
    assert many.count("print (x)") == MAX_EXPRESSIONS
    assert with_expressions("java", "class A {}", "") == "class A {}"
    with pytest.raises(ValueError):
        with_expressions("java", "class A {}", "1 + 1")


async def test_the_endpoint_sends_the_expressions_with_the_code(client: AsyncClient, db_session: AsyncSession) -> None:
    class _Seen:
        code = ""

        async def run(self, language, code, stdin):
            _Seen.code = code
            return RunResult(status="ok", stdout="", stderr="", compiler_output="", duration_ms=1)

    app.dependency_overrides[get_code_runner] = lambda: _Seen()
    headers = await _sign_in(db_session, "a@example.com")
    body = {"language": "haskell", "code": _PRIMES, "expressions": "isPrime 10"}
    assert (await client.post(URL, json=body, headers=headers)).status_code == 200
    assert _Seen.code.endswith('main = do\n  putStrLn "ghci> isPrime 10"\n  print (isPrime 10)\n')
    response = await client.post(URL, json={"language": "java", "code": "class A {}", "expressions": "1 + 1"}, headers=headers)
    assert response.status_code == 422 and "Haskell and Python only" in response.json()["detail"]


def test_haskell_expressions_that_only_look_like_commands_or_statements() -> None:
    tried = "\n".join(["[x | x <- [1..5], isPrime x]", "load 5", "reload", "line <- getLine", "(a, b) <- pure (1, 2)"])
    main = with_expressions("haskell", _PRIMES, tried).split("main = do\n")[1]
    assert "  print ([x | x <- [1..5], isPrime x])\n" in main  # a comprehension is a value
    assert "  print (load 5)\n" in main  # a call to the student's own `load`
    assert main.count("(not needed here") == 1  # only the bare `reload`
    assert "  line <- getLine\n" in main and "  (a, b) <- pure (1, 2)\n" in main

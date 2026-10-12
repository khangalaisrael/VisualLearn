"""CodeRunner: compiles and runs a student's program and returns what it printed.

The code never runs on this server. It is sent to a hosted sandbox (Wandbox,
a free community service), which is the only safe way to run arbitrary code
next to nothing of ours. Calls go through this module so the panel never
talks to the sandbox itself: the per-user limit is enforced here, and the
service can be replaced without a new extension build.
"""

import re
import time
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

Language = Literal["haskell", "java"]
RunStatus = Literal["ok", "compile_error", "runtime_error", "timeout"]

LANGUAGES: tuple[Language, ...] = ("haskell", "java")
MAX_CODE_CHARS = 20_000
MAX_STDIN_CHARS = 10_000
# What comes back is shown in a narrow panel; a runaway loop can print megabytes.
MAX_OUTPUT_CHARS = 20_000

# The sandbox's names for the compilers (GET https://wandbox.org/api/list.json).
_COMPILERS: dict[Language, str] = {"haskell": "ghc-9.10.1", "java": "openjdk-jdk-22+36"}
# The sandbox ends a program that runs too long with SIGKILL.
_KILLED_STATUS = "137"
# GHC's progress lines ("[1 of 2] Compiling Main ...", "[2 of 2] Linking ...") are not messages for the student.
_GHC_PROGRESS = re.compile(r"^\[\d+ of \d+\] (Compiling|Linking) .*\n?", re.MULTILINE)
# A top-level `public class X` must live in X.java, but the sandbox names the
# file itself. Without `public` the same program compiles and runs.
_JAVA_PUBLIC_TYPE = re.compile(r"^(\s*)public\s+((?:(?:abstract|final|strictfp|sealed|non-sealed)\s+)*(?:class|interface|enum|record)\b)", re.MULTILINE)


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    # What the program printed, and what it wrote to the error stream.
    stdout: str
    stderr: str
    # The compiler's errors and warnings.
    compiler_output: str
    duration_ms: int


class CodeRunnerUnavailable(Exception):
    """The sandbox could not be reached, or did not answer as expected."""


class CodeRunner(Protocol):
    async def run(self, language: Language, code: str, stdin: str) -> RunResult: ...


def prepare_source(language: Language, code: str) -> str:
    """The program as it is sent to the sandbox."""
    if language == "java":
        return _JAVA_PUBLIC_TYPE.sub(r"\1\2", code)
    return code


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n… (output cut off here)"


def parse_result(language: Language, payload: dict, duration_ms: int) -> RunResult:
    """Turns the sandbox's answer into ours. A compiler that reported errors
    and a program that printed nothing is a compile error; otherwise a
    non-zero exit is the program's own failure."""
    status = str(payload.get("status", ""))
    stdout = str(payload.get("program_output") or "")
    stderr = str(payload.get("program_error") or "")
    compiler = str(payload.get("compiler_error") or "")
    if language == "haskell":
        compiler = _GHC_PROGRESS.sub("", compiler)
    compiler = compiler.strip("\n")

    if status == "0":
        outcome: RunStatus = "ok"
    elif status == _KILLED_STATUS or payload.get("signal"):
        outcome = "timeout"
    elif compiler and not stdout and not stderr:
        outcome = "compile_error"
    else:
        outcome = "runtime_error"
    return RunResult(
        status=outcome,
        stdout=_clip(stdout),
        stderr=_clip(stderr),
        compiler_output=_clip(compiler),
        duration_ms=duration_ms,
    )


class WandboxCodeRunner:
    def __init__(self, url: str, timeout_seconds: float, client: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._timeout = timeout_seconds
        self._client = client

    async def run(self, language: Language, code: str, stdin: str) -> RunResult:
        body = {"compiler": _COMPILERS[language], "code": prepare_source(language, code), "stdin": stdin}
        started = time.perf_counter()
        try:
            if self._client is not None:
                response = await self._client.post(self._url, json=body, timeout=self._timeout)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self._url, json=body, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CodeRunnerUnavailable(str(exc)) from exc
        if not isinstance(payload, dict) or "status" not in payload:
            raise CodeRunnerUnavailable("unexpected answer from the sandbox")
        return parse_result(language, payload, int((time.perf_counter() - started) * 1000))


class PlaceholderCodeRunner:
    """Used by the tests: no network. Echoes the input, so a test can see what was sent."""

    async def run(self, language: Language, code: str, stdin: str) -> RunResult:
        return RunResult(status="ok", stdout=f"{language}:{stdin}", stderr="", compiler_output="", duration_ms=1)

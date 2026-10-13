"""CodeRunner: compiles and runs a student's program and returns what it printed.

The code never runs on this server. It is sent to a hosted sandbox (Wandbox,
a free community service), which is the only safe way to run arbitrary code
next to nothing of ours. Calls go through this module so the panel never
talks to the sandbox itself: the per-user limit is enforced here, and the
service can be replaced without a new extension build.
"""

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, Protocol

import httpx

Language = Literal["haskell", "java", "cpp", "python"]
RunStatus = Literal["ok", "compile_error", "runtime_error", "timeout"]

MAX_CODE_CHARS = 20_000
# What comes back is shown in a narrow panel; a runaway loop can print megabytes.
MAX_OUTPUT_CHARS = 20_000

# The sandbox's names for the compilers (GET https://wandbox.org/api/list.json).
_COMPILERS: dict[Language, str] = {
    "haskell": "ghc-9.10.1",
    "java": "openjdk-jdk-22+36",
    "cpp": "gcc-13.2.0",
    "python": "cpython-3.13.8",
}
# Extra compiler flags, as the sandbox takes them.
# - cpp: C++20, which a modern course expects.
# - haskell: link GHC's libraries dynamically. Measured on the same one-line
#   program against the sandbox, a run went from a median of 7.9 s to 4.2 s,
#   all of the linking time being saved; programs behave the same.
_COMPILER_OPTIONS: dict[Language, str] = {"cpp": "-std=c++20", "haskell": "-dynamic"}
# If the sandbox's image ever lacks the shared libraries, a Haskell program
# fails to link or load with one of these. It is then run again without the
# flag, so a change on their side costs speed, not working programs.
_DYNAMIC_LINK_FAULT = re.compile(r"cannot find -lHS|error while loading shared libraries|libHS[^ ]*[.]so")
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


class CodeRunnerBusy(CodeRunnerUnavailable):
    """The sandbox is turning requests away for now (it limits how fast one
    address may send programs, and every user of ours shares this server's)."""


# When the sandbox is overloaded it can also answer normally but with its own
# failure in place of the compiler's output ("OCI runtime error: crun: clone:
# Resource temporarily unavailable"). That is not the student's mistake.
_SANDBOX_FAULT = re.compile(r"OCI runtime error|\bcrun: |Resource temporarily unavailable|cannot fork", re.IGNORECASE)


def needs_static_link(language: Language, payload: dict) -> bool:
    """A Haskell program that failed because the dynamic libraries are not there."""
    if language != "haskell" or str(payload.get("status")) == "0":
        return False
    text = f"{payload.get('compiler_error') or ''}\n{payload.get('program_error') or ''}"
    return bool(_DYNAMIC_LINK_FAULT.search(text))


def is_sandbox_fault(payload: dict) -> bool:
    """The sandbox failed to start the program at all (nothing was printed)."""
    if payload.get("program_output"):
        return False
    text = f"{payload.get('compiler_error') or ''}\n{payload.get('program_error') or ''}"
    return bool(_SANDBOX_FAULT.search(text))


# How long to wait before asking a busy sandbox again; it recovers within seconds.
_BUSY_RETRY_DELAYS = (2.0, 5.0)


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


# Answers that are the program's own and will be the same next time. A timeout
# or a refusal says something about the sandbox's load, so it is never kept.
_CACHEABLE: frozenset[RunStatus] = frozenset({"ok", "compile_error", "runtime_error"})


class WandboxCodeRunner:
    """Runs programs on Wandbox, a free service that turns away a sender who
    is too fast. Everything here is to stay a considerate one:

    - at most `max_concurrent` programs are in flight, and one that cannot
      get a place within `queue_wait_seconds` is reported as busy;
    - once the service has refused us, no more are sent for `cooldown_seconds`
      (they are reported as busy straight away instead of hammering it);
    - an answer is kept for `cache_seconds`, so running the same program with
      the same input again costs the service nothing.

    One instance is shared by the whole server, so this state is shared too.
    """

    def __init__(
        self,
        url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        retry_delays: tuple[float, ...] = _BUSY_RETRY_DELAYS,
        *,
        max_concurrent: int = 3,
        queue_wait_seconds: float = 20.0,
        cooldown_seconds: float = 15.0,
        cache_seconds: float = 120.0,
        cache_entries: int = 200,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._timeout = timeout_seconds
        self._client = client
        self._retry_delays = retry_delays
        self._slots = asyncio.Semaphore(max(1, max_concurrent))
        self._queue_wait = queue_wait_seconds
        self._cooldown = cooldown_seconds
        self._cool_until = 0.0
        self._cache_seconds = cache_seconds
        self._cache_entries = cache_entries
        self._cache: OrderedDict[str, tuple[float, RunResult]] = OrderedDict()
        self._clock = clock

    def _key(self, body: dict) -> str:
        parts = (body["compiler"], body.get("compiler-option-raw", ""), body["code"], body["stdin"])
        return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()

    def _cached(self, key: str) -> RunResult | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires, result = entry
        if self._clock() >= expires:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return result

    def _remember(self, key: str, result: RunResult) -> None:
        if self._cache_seconds <= 0 or result.status not in _CACHEABLE:
            return
        self._cache[key] = (self._clock() + self._cache_seconds, result)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_entries:
            self._cache.popitem(last=False)

    def _check_cooldown(self) -> None:
        if self._clock() < self._cool_until:
            raise CodeRunnerBusy("the sandbox has just refused us; waiting before asking again")

    async def _post(self, body: dict) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(self._url, json=body, timeout=self._timeout)
        async with httpx.AsyncClient() as client:
            return await client.post(self._url, json=body, timeout=self._timeout)

    async def _attempt(self, body: dict) -> dict | None:
        """The sandbox's answer, or None when it is too busy to give a real one."""
        response = await self._post(body)
        if response.status_code == 429:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "status" not in payload:
            raise CodeRunnerUnavailable("unexpected answer from the sandbox")
        return None if is_sandbox_fault(payload) else payload

    async def _send(self, body: dict) -> dict:
        try:
            payload = await self._attempt(body)
            for delay in self._retry_delays:
                if payload is not None:
                    break
                await asyncio.sleep(delay)
                payload = await self._attempt(body)
        except (httpx.HTTPError, ValueError) as exc:
            raise CodeRunnerUnavailable(str(exc)) from exc
        if payload is None:
            self._cool_until = self._clock() + self._cooldown
            raise CodeRunnerBusy("the sandbox is overloaded or refusing requests for now")
        return payload

    async def run(self, language: Language, code: str, stdin: str) -> RunResult:
        body = {"compiler": _COMPILERS[language], "code": prepare_source(language, code), "stdin": stdin}
        if language in _COMPILER_OPTIONS:
            body["compiler-option-raw"] = _COMPILER_OPTIONS[language]
        started = time.perf_counter()
        key = self._key(body)
        cached = self._cached(key)
        if cached is not None:
            return replace(cached, duration_ms=int((time.perf_counter() - started) * 1000))
        self._check_cooldown()
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self._queue_wait)
        except TimeoutError as exc:
            raise CodeRunnerBusy("too many programs are waiting to run") from exc
        try:
            # A refusal may have happened while this one was waiting for a place.
            self._check_cooldown()
            # So may another run of the same program, by someone else.
            cached = self._cached(key)
            if cached is not None:
                return replace(cached, duration_ms=int((time.perf_counter() - started) * 1000))
            sent = time.perf_counter()
            payload = await self._send(body)
            if needs_static_link(language, payload):
                payload = await self._send({k: v for k, v in body.items() if k != "compiler-option-raw"})
            result = parse_result(language, payload, int((time.perf_counter() - sent) * 1000))
        finally:
            self._slots.release()
        self._remember(key, result)
        return result


class PlaceholderCodeRunner:
    """Used by the tests: no network. Echoes the input, so a test can see what was sent."""

    async def run(self, language: Language, code: str, stdin: str) -> RunResult:
        return RunResult(status="ok", stdout=f"{language}:{stdin}", stderr="", compiler_output="", duration_ms=1)

"""Trying expressions against code, the way a lecture does it in GHCi or the Python shell.

Lecture code is often a set of definitions with no main: the slide loads it
into an interpreter and types `isPrime 10`. The sandbox only compiles and
runs whole programs, so the expressions the student wants to try are turned
into the missing main: each is echoed after a prompt, evaluated after their
code, and its value printed, which reads like the session on the slide.

Nothing here runs anything: it only writes the program that is sent to the
code runner (services/code_runner.py).
"""

import json
import re

from app.services.code_runner import Language

# Languages whose lectures use an interpreter prompt.
TRYOUT_LANGUAGES: tuple[Language, ...] = ("haskell", "python")
MAX_EXPRESSIONS = 30

# Prompts copied along with an expression from a slide or a terminal.
_HASKELL_PROMPT = re.compile(r"^\s*(?:ghci>|[\w.*]*Prelude[\w.* ]*>|\*?[A-Z][\w.]*>|λ>|>)\s*")
_PYTHON_PROMPT = re.compile(r"^(?:>>>|\.\.\.) ?")
# `:load file.hs`, `:reload`, `:type x` and the like. The colon is often left
# off when typing from memory, so "load prog.hs" counts too.
_GHCI_COMMAND = re.compile(r"^(?::\S*|(?:load|reload)\b.*)(?:\s.*)?$")
# Actions that are run rather than shown.
_HASKELL_ACTION = re.compile(r"^(?:putStr|putStrLn|print|mapM_|forM_|sequence_|when|unless|main)\b")
_HASKELL_STATEMENT = re.compile(r"^(?:let\s|\S.*<-\s)")
_HASKELL_MAIN = re.compile(r"^main(?=\s*(?:::|=))", re.MULTILINE)
_HASKELL_MODULE = re.compile(r"^module\s[^\n]*?\bwhere[ \t]*$", re.MULTILINE)
_USER_MAIN = "studentMain"


def _lines(expressions: str, prompt: re.Pattern[str]) -> list[str]:
    cleaned = (prompt.sub("", line).rstrip() for line in expressions.splitlines())
    return [line for line in cleaned if line.strip()][:MAX_EXPRESSIONS]


def _haskell_string(text: str) -> str:
    """`text` as a Haskell string literal (non-ASCII is fine in GHC source)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _haskell(code: str, expressions: str) -> str:
    tried = [line.strip() for line in _lines(expressions, _HASKELL_PROMPT)]
    if not tried:
        return code
    imports = [line for line in tried if line.startswith("import ")]
    body: list[str] = []
    for line in tried:
        if line.startswith("import "):
            continue
        body.append(f"  putStrLn {_haskell_string('ghci> ' + line)}")
        if _GHCI_COMMAND.match(line):
            body.append('  putStrLn "(not needed here: your code is already loaded)"')
        elif _HASKELL_STATEMENT.match(line):
            body.append(f"  {line}")
        elif _HASKELL_ACTION.match(line):
            # The student's own `main` was renamed below, so that ours can be the entry point.
            body.append("  " + re.sub(r"^main\b", _USER_MAIN, line))
        else:
            body.append(f"  print ({line})")
    if not body:
        body.append("  return ()")

    source = _HASKELL_MAIN.sub(_USER_MAIN, code).rstrip("\n")
    if imports:
        block = "\n".join(imports) + "\n"
        module = _HASKELL_MODULE.search(source)
        source = source[: module.end()] + "\n" + block + source[module.end() :] if module else block + source
    return source + "\n\nmain :: IO ()\nmain = do\n" + "\n".join(body) + "\n"


_PYTHON_RUNNER = '''

def _try_expressions(_lines):
    for _source in _lines:
        print(">>> " + _source)
        try:
            _compiled = compile(_source, "<try>", "eval")
        except SyntaxError:
            exec(compile(_source, "<try>", "exec"), globals())
            continue
        _value = eval(_compiled, globals())
        if _value is not None:
            print(repr(_value))


_try_expressions(%s)
'''


def _python(code: str, expressions: str) -> str:
    tried = _lines(expressions, _PYTHON_PROMPT)
    if not tried:
        return code
    # A JSON list of strings is also a Python list of strings.
    return code.rstrip("\n") + _PYTHON_RUNNER % json.dumps(tried)


def with_expressions(language: Language, code: str, expressions: str) -> str:
    """`code`, followed by what it takes to evaluate `expressions` and show
    their values. Unchanged when there are none. Raises ValueError for a
    language that has no interpreter prompt to imitate."""
    if not expressions.strip():
        return code
    if language == "haskell":
        return _haskell(code, expressions)
    if language == "python":
        return _python(code, expressions)
    raise ValueError(f"Expressions cannot be tried in {language}")

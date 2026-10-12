/**
 * Code: write a program (Haskell, Java, C++ or Python), run it, and read what
 * it printed or what the compiler said. "Make it runnable" has the tutor
 * complete a fragment or correct a program that failed, then runs the result. Programs run in a hosted sandbox reached through
 * the backend (POST /code/run), never in the browser or on our server. The
 * draft for each language is kept on this device, and the result can be sent
 * to Chat to have it explained.
 *
 * The editor is a plain textarea laid over a highlighted copy of the same
 * text: the textarea's own text is transparent, so what is seen is the
 * coloured copy while typing, selection and the caret stay native. Both must
 * keep the same font, padding and line height (EDITOR_TEXT and `textStyle`),
 * and the copy follows the textarea's scroll position.
 *
 * What a key does beyond typing itself (indentation, bracket pairs, comments)
 * is decided in code/editing.ts and applied here with the browser's own
 * insert command, so Ctrl+Z undoes it like any other typing.
 */

import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CodeRunResponse } from "@shared/types";

import { ApiError, getAuthState, makeRunnable, runCode, signInWithGoogle } from "../../shared/api-client";
import { CODE_LANGUAGES, type CodeLanguage, askInChat } from "../../shared/handoff";
import { type Edit, editFor } from "../code/editing";
import { Button } from "../components/Button";
import { highlight } from "../components/CodeBlock";

/** Code handed over from an answer; `id` changes with every handover. */
export interface IncomingCode {
  id: number;
  language: CodeLanguage;
  code: string;
}

const DRAFTS_KEY = "codeDrafts";
const LANGUAGE_KEY = "codeLanguage";
const FONT_SIZE_KEY = "codeFontSize";
// Text sizes the editor offers, in pixels, and the one it starts on.
const FONT_SIZES = [12, 13, 14, 15, 16, 18];
const DEFAULT_FONT_SIZE = 14;

const STARTERS: Record<CodeLanguage, string> = {
  haskell: `double :: Int -> Int\ndouble x = x + x\n\nmain :: IO ()\nmain = print (double 21)\n`,
  java: `public class Main {\n  public static void main(String[] args) {\n    System.out.println("Hello, world");\n  }\n}\n`,
  cpp: `#include <iostream>\n\nint twice(int n) {\n  return n * 2;\n}\n\nint main() {\n  std::cout << twice(21) << std::endl;\n}\n`,
  python: `def twice(n):\n    return n * 2\n\nprint(twice(21))\n`,
};

type Drafts = Record<CodeLanguage, string>;

type RunState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; result: CodeRunResponse }
  | { status: "failed"; message: string; limited: boolean };

const HEADLINES: Record<CodeRunResponse["status"], string> = {
  ok: "Ran",
  compile_error: "Did not compile",
  runtime_error: "Stopped with an error",
  timeout: "Stopped: it ran for too long",
};

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

/** The question sent to Chat about a run: the program, then what happened. */
function tutorQuestion(language: CodeLanguage, code: string, stdin: string, result: CodeRunResponse): string {
  const name = CODE_LANGUAGES.find((item) => item.id === language)?.name ?? language;
  const parts = [
    result.status === "ok"
      ? `Explain what this ${name} program does and why it prints this output.`
      : result.status === "timeout"
        ? `This ${name} program was stopped because it ran for too long. Why does it not finish, and how do I fix it?`
        : `This ${name} program fails. Explain the error in plain words and show me how to fix it.`,
    "```" + language + "\n" + code.trimEnd() + "\n```",
  ];
  if (stdin.trim()) parts.push("Input:\n```\n" + stdin.trimEnd() + "\n```");
  if (result.compiler_output) parts.push("Compiler:\n```\n" + result.compiler_output + "\n```");
  if (result.stderr) parts.push("Error output:\n```\n" + result.stderr.trimEnd() + "\n```");
  if (result.stdout) parts.push("Output:\n```\n" + result.stdout.trimEnd() + "\n```");
  return parts.join("\n\n");
}

const FILE_NAMES: Record<CodeLanguage, string> = { haskell: "Main.hs", java: "Main.java", cpp: "main.cpp", python: "main.py" };
// A letter in a coloured chip, not a logo.
const BADGES: Record<CodeLanguage, { mark: string; className: string }> = {
  haskell: { mark: "λ", className: "bg-[#c4b5fd] text-[#1e1b4b]" },
  java: { mark: "J", className: "bg-[#fdba74] text-[#1e1b4b]" },
  cpp: { mark: "C", className: "bg-[#93c5fd] text-[#1e1b4b]" },
  python: { mark: "Py", className: "bg-[#fde68a] text-[#1e1b4b] text-[10px]" },
};
// Shared by the textarea and the highlighted copy under it: they must line up exactly.
// (Size and line height are set together in `textStyle`, since the size can be changed.)
const EDITOR_TEXT = "m-0 whitespace-pre px-3 py-2 font-mono [tab-size:2]";
const STATUS_DOTS: Record<CodeRunResponse["status"], string> = {
  ok: "bg-[#86efac]",
  compile_error: "bg-[#fca5a5]",
  runtime_error: "bg-[#fca5a5]",
  timeout: "bg-[#fde68a]",
};
const TERMINAL_LABEL = "text-[11px] font-medium text-[#8b8fd6]";
const TERMINAL_TEXT = "max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono";

/** Makes one change to the textarea through the browser's own editing command,
 * which keeps it on the undo stack and reports it to React as typing. */
function applyEdit(area: HTMLTextAreaElement, edit: Edit): void {
  if (edit.from !== edit.to || edit.insert !== "") {
    area.setSelectionRange(edit.from, edit.to);
    const done = edit.insert === "" ? document.execCommand("delete") : document.execCommand("insertText", false, edit.insert);
    if (!done) {
      // No editing command here: change the text directly and tell React.
      area.setRangeText(edit.insert, edit.from, edit.to, "end");
      area.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }
  area.setSelectionRange(edit.selectStart, edit.selectEnd);
}

function RunIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor" aria-hidden="true">
      <path d="M4 2.5v11a.5.5 0 0 0 .77.42l8.5-5.5a.5.5 0 0 0 0-.84l-8.5-5.5A.5.5 0 0 0 4 2.5Z" />
    </svg>
  );
}

export function CodeTab({ incoming, active }: { incoming: IncomingCode | null; active: boolean }): JSX.Element {
  const [language, setLanguage] = useState<CodeLanguage>("haskell");
  const [drafts, setDrafts] = useState<Drafts>(STARTERS);
  const [stdin, setStdin] = useState("");
  const [run, setRun] = useState<RunState>({ status: "idle" });
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  // How far the textarea is scrolled; the highlighted copy and the line numbers follow it.
  const [scroll, setScroll] = useState({ top: 0, left: 0 });
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
  // "Make it runnable": while the tutor works, and afterwards what it changed
  // and the student's own version, so it can be put back.
  const [fixing, setFixing] = useState(false);
  const [fix, setFix] = useState<{ note: string; language: CodeLanguage; previous: string } | null>(null);

  const code = drafts[language];

  useEffect(() => {
    chrome.storage.local
      .get([DRAFTS_KEY, LANGUAGE_KEY, FONT_SIZE_KEY])
      .then((stored) => {
        const saved = stored[DRAFTS_KEY] as Partial<Drafts> | undefined;
        if (saved) setDrafts((current) => ({ ...current, ...saved }));
        const chosen = CODE_LANGUAGES.find((item) => item.id === stored[LANGUAGE_KEY]);
        if (chosen) setLanguage(chosen.id);
        if (FONT_SIZES.includes(stored[FONT_SIZE_KEY] as number)) setFontSize(stored[FONT_SIZE_KEY] as number);
      })
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, []);

  // Drafts are kept on this device, a moment after typing stops.
  useEffect(() => {
    if (!loaded) return;
    const timer = setTimeout(() => {
      chrome.storage.local
        .set({ [DRAFTS_KEY]: drafts, [LANGUAGE_KEY]: language, [FONT_SIZE_KEY]: fontSize })
        .catch(() => undefined);
    }, 400);
    return () => clearTimeout(timer);
  }, [drafts, language, fontSize, loaded]);

  const refreshAuth = useCallback(() => {
    void getAuthState().then((auth) => setSignedIn(auth.sessionToken !== null));
  }, []);

  useEffect(() => {
    refreshAuth();
    const onChange = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "local" && changes.sessionToken) refreshAuth();
    };
    chrome.storage.onChanged.addListener(onChange);
    return () => chrome.storage.onChanged.removeListener(onChange);
  }, [refreshAuth]);

  // Code handed over from an answer replaces the draft for its language.
  useEffect(() => {
    if (!incoming) return;
    setLanguage(incoming.language);
    setDrafts((current) => ({ ...current, [incoming.language]: incoming.code }));
    setRun({ status: "idle" });
  }, [incoming]);

  useEffect(() => {
    if (active && incoming) editorRef.current?.focus();
  }, [active, incoming]);

  const setCode = (next: string) => setDrafts((current) => ({ ...current, [language]: next }));

  // A trailing newline has no height of its own in a <pre>; the space gives the last line one.
  const highlighted = useMemo(() => highlight(code, language).html + " ", [code, language]);
  const lineCount = useMemo(() => code.split("\n").length, [code]);
  // One size and one line height for the text, its coloured copy and the line numbers.
  const textStyle = { fontSize: `${fontSize}px`, lineHeight: `${Math.round(fontSize * 1.55)}px` };
  const resize = (step: number) => {
    const next = FONT_SIZES[FONT_SIZES.indexOf(fontSize) + step];
    if (next !== undefined) setFontSize(next);
  };

  const languageName = CODE_LANGUAGES.find((item) => item.id === language)?.name ?? language;

  /** Runs `source` (the editor's code unless given). */
  const execute = async (source: string = code) => {
    if (run.status === "running" || !source.trim()) return;
    setRun({ status: "running" });
    try {
      setRun({ status: "done", result: await runCode(language, source, stdin) });
    } catch (caught) {
      setRun({
        status: "failed",
        message: caught instanceof Error ? caught.message : String(caught),
        limited: caught instanceof ApiError && caught.status === 429,
      });
    }
  };

  /** Has the tutor complete or correct the code, puts the result in the editor and runs it. */
  const makeItRunnable = async () => {
    if (fixing || run.status === "running" || !code.trim()) return;
    const failed = run.status === "done" && run.result.status !== "ok" ? run.result : null;
    const lastRun = failed
      ? failed.status === "timeout"
        ? "The program was stopped because it ran for too long."
        : [failed.compiler_output, failed.stderr].filter(Boolean).join("\n")
      : "";
    setFixing(true);
    setFix(null);
    try {
      const fixed = await makeRunnable(language, code, stdin, lastRun);
      setFix({ note: fixed.note, language, previous: code });
      setCode(fixed.code);
      setFixing(false);
      if (editorRef.current) editorRef.current.scrollTop = editorRef.current.scrollLeft = 0;
      await execute(fixed.code);
    } catch (caught) {
      setRun({
        status: "failed",
        message: caught instanceof Error ? caught.message : String(caught),
        limited: caught instanceof ApiError && caught.status === 429,
      });
    } finally {
      setFixing(false);
    }
  };

  const onEditorKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void execute();
      return;
    }
    // Escape leaves the editor, so Tab (which indents here) can move on again.
    if (event.key === "Escape") {
      event.currentTarget.blur();
      return;
    }
    // While an input method is composing a character, keys belong to it.
    if (event.nativeEvent.isComposing) return;
    const area = event.currentTarget;
    const edit = editFor(
      { value: area.value, start: area.selectionStart, end: area.selectionEnd },
      { key: event.key, shift: event.shiftKey, mod: event.ctrlKey || event.metaKey, alt: event.altKey },
      language
    );
    if (edit === null) return;
    event.preventDefault();
    applyEdit(area, edit);
  };

  const signIn = async () => {
    try {
      await signInWithGoogle();
      refreshAuth();
    } catch (caught) {
      setRun({ status: "failed", message: caught instanceof Error ? caught.message : String(caught), limited: false });
    }
  };

  const result = run.status === "done" ? run.result : null;
  const nothingPrinted = result !== null && !result.stdout && !result.stderr && !result.compiler_output;

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div className="flex flex-col gap-0.5">
        <h1 className="text-base font-semibold text-slate-800">Code</h1>
        <p className="text-sm text-slate-500">Write a program, run it, and see what it prints.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={language}
          aria-label="Language"
          onChange={(event) => {
            setLanguage(event.target.value as CodeLanguage);
            setRun({ status: "idle" });
            if (editorRef.current) editorRef.current.scrollTop = editorRef.current.scrollLeft = 0;
          }}
          className="rounded-sm border border-slate-300 bg-white py-1 pl-2 pr-7 text-xs font-medium text-slate-700 focus:border-indigo-400"
        >
          {CODE_LANGUAGES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void makeItRunnable()}
          disabled={fixing || run.status === "running" || !code.trim() || signedIn === false}
          title="Have the tutor complete this code, or correct it if it failed, so that it runs"
          className="rounded-sm px-2 py-1 text-xs font-medium text-indigo-600 transition-colors duration-[120ms] hover:bg-indigo-50 disabled:opacity-50 disabled:hover:bg-transparent dark:text-indigo-300"
        >
          {fixing ? "Working on it…" : "Make it runnable"}
        </button>
        <button
          type="button"
          onClick={() => {
            if (code.trim() && code !== STARTERS[language] && !window.confirm("Replace your code with the starting example?")) return;
            setCode(STARTERS[language]);
            setRun({ status: "idle" });
            setFix(null);
          }}
          className="rounded-sm px-2 py-1 text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700"
        >
          Reset
        </button>
        <div className="ml-auto flex items-center gap-1" role="group" aria-label="Text size">
          <button
            type="button"
            onClick={() => resize(-1)}
            disabled={fontSize === FONT_SIZES[0]}
            aria-label="Smaller text"
            title="Smaller text"
            className="flex h-7 w-7 items-center justify-center rounded-sm text-xs font-semibold text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 disabled:hover:bg-transparent"
          >
            A−
          </button>
          <button
            type="button"
            onClick={() => resize(1)}
            disabled={fontSize === FONT_SIZES[FONT_SIZES.length - 1]}
            aria-label="Larger text"
            title="Larger text"
            className="flex h-7 w-7 items-center justify-center rounded-sm text-base font-semibold text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 disabled:hover:bg-transparent"
          >
            A+
          </button>
        </div>
      </div>

      <div className="vl-editor flex-none overflow-hidden rounded-md border border-[#3730a3] shadow-subtle focus-within:ring-2 focus-within:ring-indigo-300">
        <div className="flex items-center gap-2 bg-[var(--vl-editor-bar)] py-1.5 pl-3 pr-1.5">
          <span
            className={`flex h-5 w-5 flex-none items-center justify-center rounded-sm font-mono text-xs font-bold ${BADGES[language].className}`}
            aria-hidden="true"
          >
            {BADGES[language].mark}
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--vl-editor-text)]">{FILE_NAMES[language]}</span>
          <button
            type="button"
            onClick={() => void execute()}
            disabled={run.status === "running" || fixing || !code.trim() || signedIn === false}
            className="flex flex-none items-center gap-1.5 rounded-sm bg-[var(--vl-editor-warm)] px-3 py-1 text-xs font-semibold text-[#1e1b4b] transition-colors duration-[120ms] hover:bg-[#fef3c7] active:bg-[#fcd34d] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RunIcon />
            {run.status === "running" ? "Running…" : "Run"}
          </button>
        </div>
        <div className="relative flex h-72 min-h-[7rem] resize-y overflow-hidden bg-[var(--vl-editor-bg)]">
          <div className="flex-none select-none overflow-hidden border-r border-white/10 py-2 pl-2 pr-2 text-right font-mono text-[var(--vl-editor-dim)]" style={textStyle} aria-hidden="true">
            <div style={{ transform: `translateY(${-scroll.top}px)` }}>
              {Array.from({ length: lineCount }, (_, index) => (
                <div key={index}>{index + 1}</div>
              ))}
            </div>
          </div>
          <div className="relative min-w-0 flex-1 overflow-hidden">
            <pre
              aria-hidden="true"
              className={`${EDITOR_TEXT} hljs pointer-events-none absolute left-0 top-0 text-[var(--vl-editor-text)]`}
              style={{ ...textStyle, transform: `translate(${-scroll.left}px, ${-scroll.top}px)` }}
              // eslint-disable-next-line react/no-danger -- hljs.highlight's own output, which escapes the code
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
            <textarea
              ref={editorRef}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              onKeyDown={onEditorKey}
              onScroll={(event) => setScroll({ top: event.currentTarget.scrollTop, left: event.currentTarget.scrollLeft })}
              aria-label={`Your ${languageName} code`}
              wrap="off"
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              maxLength={20000}
              style={textStyle}
              className={`${EDITOR_TEXT} scrollbar-thin absolute inset-0 h-full w-full resize-none overflow-auto border-0 bg-transparent text-transparent caret-[var(--vl-editor-warm)] outline-none focus:ring-0`}
            />
          </div>
        </div>
      </div>

      <details className="rounded-sm border border-slate-200 px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium text-slate-600">Program input{stdin ? " (set)" : ""}</summary>
        <textarea
          value={stdin}
          onChange={(event) => setStdin(event.target.value)}
          spellCheck={false}
          rows={3}
          maxLength={10000}
          aria-label="Program input"
          placeholder="What the program reads, such as numbers it asks for. One value per line."
          className="mt-2 w-full resize-y rounded-sm border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-800 placeholder:font-sans placeholder:text-slate-400 focus:border-indigo-400"
        />
      </details>

      {fixing && (
        <p className="animate-pulse text-xs text-slate-400" role="status">
          The tutor is completing your code. This takes a few seconds.
        </p>
      )}

      {fix && fix.language === language && (
        <div role="status" className="flex flex-col items-start gap-2 rounded-md border border-amber-100 bg-amber-50/70 p-3 dark:border-indigo-100 dark:bg-indigo-50/40">
          <p className="text-sm leading-relaxed text-slate-700">
            <span className="font-semibold">Made runnable.</span> {fix.note}
          </p>
          <button
            type="button"
            onClick={() => {
              setCode(fix.previous);
              setFix(null);
              setRun({ status: "idle" });
            }}
            className="rounded-sm text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
          >
            Put my version back
          </button>
        </div>
      )}

      {signedIn === false && (
        <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-slate-200 p-3">
          <p className="text-sm text-slate-600">Sign in to run code. Your draft stays here either way.</p>
          <Button onClick={() => void signIn()}>Sign in with Google</Button>
        </div>
      )}

      {run.status === "running" && (
        <p className="animate-pulse text-xs text-slate-400" role="status">
          Compiling and running. This takes a few seconds.
        </p>
      )}

      {run.status === "failed" &&
        (run.limited ? (
          <p role="status" className="rounded-md border border-violet-100 bg-violet-50/50 p-3 text-sm text-slate-600">
            {run.message}
          </p>
        ) : (
          <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
            {run.message}
          </p>
        ))}

      {result && (
        <div className="flex flex-col gap-2">
          <section className="vl-editor flex-none overflow-hidden rounded-md border border-[#3730a3] shadow-subtle" aria-label="Result">
            <div className="flex items-center gap-2 bg-[var(--vl-editor-bar)] px-3 py-1.5">
              <span className={`h-2 w-2 flex-none rounded-full ${STATUS_DOTS[result.status]}`} aria-hidden="true" />
              <p role="status" className="text-xs text-[var(--vl-editor-text)]">
                <span className="font-semibold">{HEADLINES[result.status]}</span> in {seconds(result.duration_ms)}
              </p>
            </div>
            <div className="flex flex-col gap-3 bg-[var(--vl-editor-bg)] px-3 py-2">
              {result.compiler_output && (
                <div className="flex flex-col gap-1">
                  <h2 className={TERMINAL_LABEL}>{result.status === "compile_error" ? "Compiler errors" : "Compiler messages"}</h2>
                  <pre style={textStyle} className={`${TERMINAL_TEXT} ${result.status === "compile_error" ? "text-[#fca5a5]" : "text-[var(--vl-editor-warm)]"}`}>
                    {result.compiler_output}
                  </pre>
                </div>
              )}
              {result.stdout && (
                <div className="flex flex-col gap-1">
                  <h2 className={TERMINAL_LABEL}>Output</h2>
                  <pre style={textStyle} className={`${TERMINAL_TEXT} text-[var(--vl-editor-text)]`}>{result.stdout}</pre>
                </div>
              )}
              {result.stderr && (
                <div className="flex flex-col gap-1">
                  <h2 className={TERMINAL_LABEL}>Error output</h2>
                  <pre style={textStyle} className={`${TERMINAL_TEXT} text-[#fca5a5]`}>{result.stderr}</pre>
                </div>
              )}
              {nothingPrinted && <p className="font-mono text-xs text-[var(--vl-editor-dim)]">The program printed nothing.</p>}
            </div>
          </section>
          <div className="flex flex-wrap items-center gap-2">
            {result.status !== "ok" && (
              <Button onClick={() => void makeItRunnable()} disabled={fixing}>
                {fixing ? "Working on it…" : "Make it runnable"}
              </Button>
            )}
            <Button variant="secondary" onClick={() => askInChat(tutorQuestion(language, code, stdin, result))}>
              {result.status === "ok" ? "Ask the tutor to explain this" : "Ask the tutor about this error"}
            </Button>
          </div>
        </div>
      )}

      <p className="mt-auto text-xs text-slate-400">
        Ctrl+Enter runs, Ctrl+/ comments a line, Tab and Shift+Tab indent. Programs run on wandbox.org, an outside
        service, and are stopped after about 30 seconds. Keep passwords and private data out of them.
      </p>
    </div>
  );
}

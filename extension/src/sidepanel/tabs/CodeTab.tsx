/**
 * Code: write a program (Haskell, Java, C++ or Python), run it, and read what
 * it printed or what the compiler said, laid out like a small IDE: a toolbar,
 * the editor filling the space, a docked panel below it (Output, Input, Try,
 * Tutor) whose height can be dragged, and a status bar.
 *
 * "Make it runnable" has the tutor complete a fragment or correct a program
 * that failed, then runs the result. Haskell and Python also take expressions
 * to try, as a lecture does in GHCi or the Python shell: code from a slide
 * rarely has a main of its own. Programs run in a hosted sandbox reached
 * through the backend (POST /code/run), never in the browser or on our
 * server. The draft for each language is kept on this device.
 *
 * Compiler errors and tracebacks are read for the lines they name
 * (code/diagnostics.ts): those lines are underlined in the editor, and every
 * place named in the output can be clicked to jump there.
 */

import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CodeRunResponse } from "@shared/types";

import { ApiError, getAuthState, makeRunnable, runCode, signInWithGoogle } from "../../shared/api-client";
import { CODE_LANGUAGES, type CodeLanguage } from "../../shared/handoff";
import { CodeTutor } from "../code/CodeTutor";
import { linkLocations, parseDiagnostics } from "../code/diagnostics";
import { type CursorPosition, Editor, type EditorHandle } from "../code/Editor";
import { Button } from "../components/Button";

/** Code handed over from an answer; `id` changes with every handover. */
export interface IncomingCode {
  id: number;
  language: CodeLanguage;
  code: string;
}

const DRAFTS_KEY = "codeDrafts";
const LANGUAGE_KEY = "codeLanguage";
const FONT_SIZE_KEY = "codeFontSize";
const TRIES_KEY = "codeTries";
const PANEL_KEY = "codePanelHeight";

// Languages a lecture uses through an interpreter prompt, and how that is described.
const TRY_HELP: Partial<Record<CodeLanguage, { where: string; example: string }>> = {
  haskell: { where: "GHCi", example: "isPrime 10\nprimes 30" },
  python: { where: "the Python shell", example: "twice(21)\n[twice(n) for n in range(3)]" },
};
// Text sizes the editor offers, in pixels, and the one it starts on.
const FONT_SIZES = [12, 13, 14, 15, 16, 18];
const DEFAULT_FONT_SIZE = 13;

const STARTERS: Record<CodeLanguage, string> = {
  haskell: `double :: Int -> Int\ndouble x = x + x\n\nmain :: IO ()\nmain = print (double 21)\n`,
  java: `public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, world");\n    }\n}\n`,
  cpp: `#include <iostream>\n\nint twice(int n) {\n    return n * 2;\n}\n\nint main() {\n    std::cout << twice(21) << std::endl;\n}\n`,
  python: `def twice(n):\n    return n * 2\n\nprint(twice(21))\n`,
};

type Drafts = Record<CodeLanguage, string>;
type PanelTab = "output" | "input" | "try" | "tutor";

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

/** The code, and what happened when it last ran, as the tutor is told it. */
function tutorContext(
  language: CodeLanguage,
  code: string,
  stdin: string,
  expressions: string,
  result: CodeRunResponse | null
): string {
  const name = CODE_LANGUAGES.find((item) => item.id === language)?.name ?? language;
  const outcome =
    result === null
      ? "I have not run it yet."
      : result.status === "ok"
        ? "It ran."
        : result.status === "compile_error"
          ? "It did not compile."
          : result.status === "timeout"
            ? "It was stopped because it ran for too long."
            : "It stopped with an error.";
  const parts = [`This is my ${name} code. ${outcome}`, "```" + language + "\n" + code.trimEnd() + "\n```"];
  if (expressions.trim()) parts.push("Expressions I tried, one per line:\n```\n" + expressions.trimEnd() + "\n```");
  if (stdin.trim()) parts.push("Input:\n```\n" + stdin.trimEnd() + "\n```");
  if (result?.compiler_output) parts.push("Compiler:\n```\n" + result.compiler_output + "\n```");
  if (result?.stderr) parts.push("Error output:\n```\n" + result.stderr.trimEnd() + "\n```");
  if (result?.stdout) parts.push("Output:\n```\n" + result.stdout.trimEnd() + "\n```");
  return parts.join("\n\n");
}

/** One-press questions that fit how the last run went. */
function suggestionsFor(result: CodeRunResponse | null): string[] {
  if (result === null) return ["Explain this code"];
  if (result.status === "ok") return ["Why this output?", "Explain this code"];
  if (result.status === "timeout") return ["Why does it not finish?", "How do I fix it?"];
  return ["Explain this error", "How do I fix it?"];
}

const FILE_NAMES: Record<CodeLanguage, string> = { haskell: "Main.hs", java: "Main.java", cpp: "main.cpp", python: "main.py" };
// A letter in a coloured chip, not a logo.
const BADGES: Record<CodeLanguage, { mark: string; className: string }> = {
  haskell: { mark: "λ", className: "bg-[#c4b5fd] text-[#1e1b4b]" },
  java: { mark: "J", className: "bg-[#fdba74] text-[#1e1b4b]" },
  cpp: { mark: "C", className: "bg-[#93c5fd] text-[#1e1b4b]" },
  python: { mark: "Py", className: "bg-[#fde68a] text-[#1e1b4b] text-[10px]" },
};
const STATUS_DOTS: Record<CodeRunResponse["status"], string> = {
  ok: "bg-[#86efac]",
  compile_error: "bg-[#fca5a5]",
  runtime_error: "bg-[#fca5a5]",
  timeout: "bg-[#fde68a]",
};
const TERMINAL_LABEL = "text-[11px] font-medium uppercase tracking-wide text-[var(--vl-editor-dim)]";
const TERMINAL_TEXT = "whitespace-pre-wrap break-words font-mono [font-variant-ligatures:none]";
const DEFAULT_PANEL = 240;
const MIN_PANEL = 120;
const MIN_EDITOR = 140;
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = IS_MAC ? "⌘" : "Ctrl";

function RunIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor" aria-hidden="true">
      <path d="M4 2.5v11a.5.5 0 0 0 .77.42l8.5-5.5a.5.5 0 0 0 0-.84l-8.5-5.5A.5.5 0 0 0 4 2.5Z" />
    </svg>
  );
}

function MoreIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor" aria-hidden="true">
      <circle cx="3.5" cy="8" r="1.3" />
      <circle cx="8" cy="8" r="1.3" />
      <circle cx="12.5" cy="8" r="1.3" />
    </svg>
  );
}

function Chevron({ up }: { up: boolean }): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" className={`h-3.5 w-3.5 transition-transform ${up ? "" : "rotate-180"}`} fill="none" aria-hidden="true">
      <path d="M4 10l4-4 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Output text with every place in the code it names turned into a link to that line. */
function Located({ text, lineCount, onGo, className }: { text: string; lineCount: number; onGo: (line: number) => void; className: string }): JSX.Element {
  return (
    <pre className={className}>
      {linkLocations(text, lineCount).map((part, index) =>
        "line" in part ? (
          <button
            key={index}
            type="button"
            onClick={() => onGo(part.line)}
            title={`Go to line ${part.line}`}
            className="rounded-sm underline decoration-dotted underline-offset-2 hover:bg-white/10 hover:decoration-solid"
          >
            {part.text}
          </button>
        ) : (
          <span key={index}>{part.text}</span>
        )
      )}
    </pre>
  );
}

export function CodeTab({ incoming, active }: { incoming: IncomingCode | null; active: boolean }): JSX.Element {
  const [language, setLanguage] = useState<CodeLanguage>("haskell");
  const [drafts, setDrafts] = useState<Drafts>(STARTERS);
  const [stdin, setStdin] = useState("");
  // Expressions to try after the code, per language (see TRY_HELP).
  const [tries, setTries] = useState<Partial<Record<CodeLanguage, string>>>({});
  const [run, setRun] = useState<RunState>({ status: "idle" });
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
  const [cursor, setCursor] = useState<CursorPosition>({ line: 1, column: 1, selected: 0 });
  const [panel, setPanel] = useState<PanelTab>("output");
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelHeight, setPanelHeight] = useState(DEFAULT_PANEL);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [tutorQuestion, setTutorQuestion] = useState<{ id: number; text: string } | null>(null);
  // "Make it runnable": while the tutor works, and afterwards what it changed
  // and the student's own version, so it can be put back.
  const [fixing, setFixing] = useState(false);
  const [fix, setFix] = useState<{ note: string; language: CodeLanguage; previous: string } | null>(null);
  const editorRef = useRef<EditorHandle | null>(null);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const code = drafts[language];
  const lineCount = useMemo(() => code.split("\n").length, [code]);

  useEffect(() => {
    chrome.storage.local
      .get([DRAFTS_KEY, LANGUAGE_KEY, FONT_SIZE_KEY, TRIES_KEY, PANEL_KEY])
      .then((stored) => {
        const saved = stored[DRAFTS_KEY] as Partial<Drafts> | undefined;
        if (saved) setDrafts((current) => ({ ...current, ...saved }));
        if (stored[TRIES_KEY]) setTries(stored[TRIES_KEY] as Partial<Record<CodeLanguage, string>>);
        const chosen = CODE_LANGUAGES.find((item) => item.id === stored[LANGUAGE_KEY]);
        if (chosen) setLanguage(chosen.id);
        if (FONT_SIZES.includes(stored[FONT_SIZE_KEY] as number)) setFontSize(stored[FONT_SIZE_KEY] as number);
        if (typeof stored[PANEL_KEY] === "number") setPanelHeight(stored[PANEL_KEY] as number);
      })
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, []);

  // Drafts and layout are kept on this device, a moment after typing stops.
  useEffect(() => {
    if (!loaded) return;
    const timer = setTimeout(() => {
      chrome.storage.local
        .set({ [DRAFTS_KEY]: drafts, [LANGUAGE_KEY]: language, [FONT_SIZE_KEY]: fontSize, [TRIES_KEY]: tries, [PANEL_KEY]: panelHeight })
        .catch(() => undefined);
    }, 400);
    return () => clearTimeout(timer);
  }, [drafts, language, fontSize, tries, panelHeight, loaded]);

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
    // Expressions written for the code that was here do not belong to the new code.
    setTries((current) => ({ ...current, [incoming.language]: "" }));
    setRun({ status: "idle" });
    setFix(null);
  }, [incoming]);

  useEffect(() => {
    if (active && incoming) editorRef.current?.focus();
  }, [active, incoming]);

  // The ⋯ menu closes on a click anywhere else, or Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
        setConfirmReset(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        setConfirmReset(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const setCode = useCallback((next: string) => setDrafts((current) => ({ ...current, [language]: next })), [language]);
  const resize = (step: number) => {
    const next = FONT_SIZES[FONT_SIZES.indexOf(fontSize) + step];
    if (next !== undefined) setFontSize(next);
  };

  const languageName = CODE_LANGUAGES.find((item) => item.id === language)?.name ?? language;
  const tryHelp = TRY_HELP[language];
  const expressions = tryHelp ? (tries[language] ?? "") : "";
  const result = run.status === "done" ? run.result : null;

  const diagnostics = useMemo(
    () => (result && result.status !== "ok" ? parseDiagnostics(`${result.compiler_output}\n${result.stderr}`, lineCount) : []),
    // Only a new result moves the marks; edits after it are tracked by the editor itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result]
  );

  const showPanel = (tab: PanelTab) => {
    setPanel(tab);
    setPanelOpen(true);
  };

  /** Runs `source` (the editor's code unless given), with the expressions to try unless told not to. */
  const execute = async (source: string = code, tryExpressions: boolean = true) => {
    if (run.status === "running" || fixing || !source.trim() || signedIn === false) return;
    setRun({ status: "running" });
    showPanel("output");
    try {
      setRun({ status: "done", result: await runCode(language, source, stdin, tryExpressions ? expressions : "") });
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
    if (fixing || run.status === "running" || !code.trim() || signedIn === false) return;
    const failed = run.status === "done" && run.result.status !== "ok" ? run.result : null;
    const lastRun = failed
      ? failed.status === "timeout"
        ? "The program was stopped because it ran for too long."
        : [failed.compiler_output, failed.stderr].filter(Boolean).join("\n")
      : "";
    setFixing(true);
    setFix(null);
    showPanel("output");
    try {
      const fixed = await makeRunnable(language, code, stdin, lastRun);
      setFix({ note: fixed.note, language, previous: code });
      setCode(fixed.code);
      setFixing(false);
      // The completed program is run as a program: it has a main of its own now,
      // and the expressions may have been written for something else.
      setRun({ status: "running" });
      try {
        setRun({ status: "done", result: await runCode(language, fixed.code, stdin, "") });
      } catch (caught) {
        setRun({
          status: "failed",
          message: caught instanceof Error ? caught.message : String(caught),
          limited: caught instanceof ApiError && caught.status === 429,
        });
      }
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

  const askTutor = (text: string) => {
    setTutorQuestion({ id: Date.now(), text });
    showPanel("tutor");
  };

  const signIn = async () => {
    try {
      await signInWithGoogle();
      refreshAuth();
    } catch (caught) {
      setRun({ status: "failed", message: caught instanceof Error ? caught.message : String(caught), limited: false });
    }
  };

  const goToLine = (line: number) => editorRef.current?.goToLine(line);

  // Dragging the bar between the editor and the panel.
  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const layout = layoutRef.current;
    if (!layout) return;
    event.preventDefault();
    const bar = event.currentTarget;
    bar.setPointerCapture(event.pointerId);
    const bottom = layout.getBoundingClientRect().bottom;
    const move = (moveEvent: PointerEvent) => {
      const room = layout.clientHeight - MIN_EDITOR;
      setPanelHeight(Math.round(Math.min(Math.max(bottom - moveEvent.clientY, MIN_PANEL), Math.max(MIN_PANEL, room))));
      setPanelOpen(true);
    };
    const end = () => {
      bar.removeEventListener("pointermove", move);
      bar.removeEventListener("pointerup", end);
      bar.removeEventListener("pointercancel", end);
    };
    bar.addEventListener("pointermove", move);
    bar.addEventListener("pointerup", end);
    bar.addEventListener("pointercancel", end);
  };

  const running = run.status === "running";
  const canRun = !running && !fixing && Boolean(code.trim()) && signedIn !== false;
  const nothingPrinted = result !== null && !result.stdout && !result.stderr && !result.compiler_output;
  const errorCount = diagnostics.filter((item) => item.severity === "error").length;
  const noMain = result?.status === "compile_error" && tryHelp && !expressions.trim() && /main.{0,3} is not defined/.test(result.compiler_output);

  const tabs: { id: PanelTab; label: string; badge?: string }[] = [
    { id: "output", label: "Output" },
    { id: "input", label: "Input", badge: stdin.trim() ? "●" : undefined },
    ...(tryHelp ? [{ id: "try" as const, label: "Try", badge: expressions.trim() ? String(expressions.trim().split("\n").length) : undefined }] : []),
    { id: "tutor", label: "Tutor" },
  ];
  const panelTab = tabs.some((tab) => tab.id === panel) ? panel : "output";

  return (
    <div className="vl-editor flex min-h-0 flex-1 flex-col bg-[var(--vl-editor-bg)]">
      {/* Toolbar */}
      <div className="flex flex-none items-center gap-1.5 border-b border-white/10 bg-[var(--vl-editor-bar)] px-2 py-1.5">
        <label className="relative flex min-w-0 items-center gap-1.5 rounded-sm py-1 pl-1.5 pr-1 hover:bg-white/10">
          <span
            className={`flex h-5 w-5 flex-none items-center justify-center rounded-sm font-mono text-xs font-bold ${BADGES[language].className}`}
            aria-hidden="true"
          >
            {BADGES[language].mark}
          </span>
          <select
            value={language}
            aria-label="Language"
            title="Language"
            onChange={(event) => {
              setLanguage(event.target.value as CodeLanguage);
              setRun({ status: "idle" });
            }}
            className="min-w-0 cursor-pointer appearance-none border-0 bg-transparent py-0 pl-0 pr-4 font-mono text-xs text-[var(--vl-editor-text)] focus:ring-0"
          >
            {CODE_LANGUAGES.map((item) => (
              <option key={item.id} value={item.id} className="bg-white font-sans text-slate-800">
                {item.name}
              </option>
            ))}
          </select>
          <svg viewBox="0 0 16 16" className="pointer-events-none absolute right-1 h-3 w-3 text-[var(--vl-editor-dim)]" fill="none" aria-hidden="true">
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </label>

        <span className="hidden min-w-0 truncate font-mono text-[11px] text-[var(--vl-editor-dim)] min-[380px]:inline">{FILE_NAMES[language]}</span>

        <div className="ml-auto flex flex-none items-center gap-1">
          <button
            type="button"
            onClick={() => void makeItRunnable()}
            disabled={fixing || running || !code.trim() || signedIn === false}
            title="Have the tutor complete this code, or correct it if it failed, so that it runs"
            className="rounded-sm px-2 py-1 text-xs font-medium text-[var(--vl-editor-text)] transition-colors duration-[120ms] hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent"
          >
            {fixing ? "Fixing…" : "Make runnable"}
          </button>
          <button
            type="button"
            onClick={() => void execute()}
            disabled={!canRun}
            title={`Run (${MOD}+Enter)`}
            className="flex items-center gap-1.5 rounded-sm bg-[var(--vl-editor-warm)] px-3 py-1 text-xs font-semibold text-[#1e1b4b] transition-colors duration-[120ms] hover:bg-[#fef3c7] active:bg-[#fcd34d] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RunIcon />
            {running ? "Running…" : "Run"}
          </button>
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen((open) => !open);
                setConfirmReset(false);
              }}
              aria-label="More options"
              aria-expanded={menuOpen}
              title="More options"
              className="flex h-7 w-7 items-center justify-center rounded-sm text-[var(--vl-editor-text)] transition-colors duration-[120ms] hover:bg-white/10"
            >
              <MoreIcon />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-8 z-20 flex w-60 flex-col gap-1 rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-700 shadow-lg"
              >
                <div className="flex items-center justify-between px-1 py-1">
                  <span className="text-xs text-slate-500">Text size</span>
                  <span className="flex items-center gap-1" role="group" aria-label="Text size">
                    <button
                      type="button"
                      onClick={() => resize(-1)}
                      disabled={fontSize === FONT_SIZES[0]}
                      aria-label="Smaller text"
                      className="flex h-7 w-7 items-center justify-center rounded-sm text-xs font-semibold hover:bg-slate-100 disabled:opacity-40"
                    >
                      A−
                    </button>
                    <span className="w-6 text-center text-xs tabular-nums text-slate-500">{fontSize}</span>
                    <button
                      type="button"
                      onClick={() => resize(1)}
                      disabled={fontSize === FONT_SIZES[FONT_SIZES.length - 1]}
                      aria-label="Larger text"
                      className="flex h-7 w-7 items-center justify-center rounded-sm text-base font-semibold hover:bg-slate-100 disabled:opacity-40"
                    >
                      A+
                    </button>
                  </span>
                </div>
                {confirmReset ? (
                  <div className="flex flex-col gap-2 rounded-sm bg-slate-50 p-2">
                    <p className="text-xs text-slate-600">Replace your {languageName} code with the starting example?</p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setCode(STARTERS[language]);
                          setTries((current) => ({ ...current, [language]: "" }));
                          setRun({ status: "idle" });
                          setFix(null);
                          setMenuOpen(false);
                          setConfirmReset(false);
                        }}
                        className="rounded-sm bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
                      >
                        Replace
                      </button>
                      <button type="button" onClick={() => setConfirmReset(false)} className="rounded-sm px-2.5 py-1 text-xs font-medium hover:bg-slate-200">
                        Keep my code
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => (code === STARTERS[language] ? setMenuOpen(false) : setConfirmReset(true))}
                    className="rounded-sm px-2 py-1.5 text-left text-xs hover:bg-slate-100"
                  >
                    Start again from the example
                  </button>
                )}
                <div className="border-t border-slate-100 px-2 pb-1 pt-2 text-[11px] leading-relaxed text-slate-500">
                  <p className="mb-1 font-medium text-slate-600">Keyboard</p>
                  <p>{MOD}+Enter run · {MOD}+/ comment</p>
                  <p>{MOD}+F find · {MOD}+Z undo · Alt+↑↓ move line</p>
                  <p>Tab indent · Esc then Tab leaves the editor</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Notices */}
      {signedIn === false && (
        <div className="flex flex-none items-center gap-3 bg-white px-3 py-2 text-sm text-slate-600">
          <p className="min-w-0 flex-1">Sign in to run code. Your draft stays here either way.</p>
          <Button className="flex-none" onClick={() => void signIn()}>
            Sign in
          </Button>
        </div>
      )}
      {fix && fix.language === language && (
        <div role="status" className="flex flex-none items-start gap-2 border-b border-amber-200/30 bg-[#3b3270] px-3 py-2 text-xs leading-relaxed text-[var(--vl-editor-text)]">
          <p className="min-w-0 flex-1">
            <span className="font-semibold text-[var(--vl-editor-warm)]">Made runnable.</span> {fix.note}
          </p>
          <button
            type="button"
            onClick={() => {
              setCode(fix.previous);
              setFix(null);
              setRun({ status: "idle" });
            }}
            className="flex-none rounded-sm px-1.5 py-0.5 font-medium underline-offset-2 hover:underline"
          >
            Undo
          </button>
          <button type="button" onClick={() => setFix(null)} aria-label="Dismiss" className="flex-none rounded-sm px-1.5 py-0.5 hover:bg-white/10">
            ✕
          </button>
        </div>
      )}

      <div ref={layoutRef} className="flex min-h-0 flex-1 flex-col">
        {/* Editor */}
        <div className="min-h-0 flex-1">
          <Editor
            ref={editorRef}
            value={code}
            language={language}
            fontSize={fontSize}
            diagnostics={diagnostics}
            ariaLabel={`Your ${languageName} code`}
            onChange={setCode}
            onRun={() => void execute()}
            onCursor={setCursor}
          />
        </div>

        {/* Panel */}
        <div className="flex flex-none flex-col border-t border-white/10" style={panelOpen ? { height: panelHeight } : undefined}>
          {panelOpen && (
            <div
              role="separator"
              tabIndex={0}
              aria-orientation="horizontal"
              aria-label="Resize the panel"
              aria-valuenow={panelHeight}
              aria-valuemin={MIN_PANEL}
              title="Drag up or down to resize. Double-click to reset."
              onPointerDown={startDrag}
              onDoubleClick={() => setPanelHeight(DEFAULT_PANEL)}
              onKeyDown={(event) => {
                if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                event.preventDefault();
                const room = Math.max(MIN_PANEL, (layoutRef.current?.clientHeight ?? 600) - MIN_EDITOR);
                const next = panelHeight + (event.key === "ArrowUp" ? 32 : -32);
                setPanelHeight(Math.min(Math.max(next, MIN_PANEL), room));
              }}
              className="group relative flex h-3.5 flex-none cursor-row-resize touch-none items-center justify-center bg-white/[0.06] outline-none before:absolute before:inset-x-0 before:-top-2 before:bottom-[-0.5rem] before:content-[''] hover:bg-indigo-400/25 focus-visible:bg-indigo-400/30 active:bg-indigo-400/35"
            >
              <span className="h-1 w-12 rounded-full bg-white/35 transition-colors group-hover:bg-white/70 group-focus-visible:bg-white/80" aria-hidden="true" />
            </div>
          )}
          <div className="flex flex-none items-center gap-0.5 bg-[var(--vl-editor-bar)] px-1.5" role="tablist" aria-label="Panel">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={panelOpen && panelTab === tab.id}
                onClick={() => (panelOpen && panelTab === tab.id ? setPanelOpen(false) : showPanel(tab.id))}
                className={`flex items-center gap-1 border-b-2 px-2.5 py-1.5 text-xs font-medium transition-colors duration-[120ms] ${
                  panelOpen && panelTab === tab.id
                    ? "border-[var(--vl-editor-warm)] text-[var(--vl-editor-text)]"
                    : "border-transparent text-[var(--vl-editor-dim)] hover:text-[var(--vl-editor-text)]"
                }`}
              >
                {tab.id === "output" && result && <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOTS[result.status]}`} aria-hidden="true" />}
                {tab.label}
                {tab.badge && <span className="text-[10px] text-[var(--vl-editor-warm)]">{tab.badge}</span>}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPanelOpen((open) => !open)}
              aria-label={panelOpen ? "Hide the panel" : "Show the panel"}
              title={panelOpen ? "Hide the panel" : "Show the panel"}
              className="ml-auto flex h-6 w-6 items-center justify-center rounded-sm text-[var(--vl-editor-dim)] hover:bg-white/10 hover:text-[var(--vl-editor-text)]"
            >
              <Chevron up={!panelOpen} />
            </button>
          </div>

          <div className={panelOpen ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
            {panelTab === "output" && (
              <div className="scrollbar-thin flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-2 text-[var(--vl-editor-text)]" style={{ fontSize: Math.max(12, fontSize - 1) }}>
                {run.status === "idle" && !fixing && (
                  <p className="text-xs leading-relaxed text-[var(--vl-editor-dim)]">
                    Press Run or {MOD}+Enter. What the program prints appears here. Programs run on wandbox.org, an outside
                    service, and are stopped after about 30 seconds, so keep passwords and private data out of them.
                  </p>
                )}
                {fixing && (
                  <p className="animate-pulse text-xs text-[var(--vl-editor-dim)]" role="status">
                    The tutor is completing your code. This takes a few seconds.
                  </p>
                )}
                {running && (
                  <p className="animate-pulse text-xs text-[var(--vl-editor-dim)]" role="status">
                    Compiling and running…
                  </p>
                )}
                {run.status === "failed" && (
                  <p role={run.limited ? "status" : "alert"} className={`text-sm ${run.limited ? "text-[var(--vl-editor-text)]" : "text-[#fca5a5]"}`}>
                    {run.message}
                  </p>
                )}
                {result && (
                  <>
                    <p role="status" className="flex items-center gap-2 text-xs text-[var(--vl-editor-dim)]">
                      <span className={`h-2 w-2 flex-none rounded-full ${STATUS_DOTS[result.status]}`} aria-hidden="true" />
                      <span>
                        <span className="font-semibold text-[var(--vl-editor-text)]">{HEADLINES[result.status]}</span> in {seconds(result.duration_ms)}
                        {errorCount > 0 && ` · ${errorCount === 1 ? "1 error" : `${errorCount} errors`} marked in the code`}
                      </span>
                    </p>
                    {result.compiler_output && (
                      <div className="flex flex-col gap-1">
                        <h2 className={TERMINAL_LABEL}>{result.status === "compile_error" ? "Compiler errors" : "Compiler messages"}</h2>
                        <Located
                          text={result.compiler_output}
                          lineCount={lineCount}
                          onGo={goToLine}
                          className={`${TERMINAL_TEXT} ${result.status === "compile_error" ? "text-[#fca5a5]" : "text-[var(--vl-editor-warm)]"}`}
                        />
                      </div>
                    )}
                    {result.stdout && (
                      <div className="flex flex-col gap-1">
                        {(result.compiler_output || result.stderr) && <h2 className={TERMINAL_LABEL}>Output</h2>}
                        <pre className={`${TERMINAL_TEXT} text-[var(--vl-editor-text)]`}>{result.stdout}</pre>
                      </div>
                    )}
                    {result.stderr && (
                      <div className="flex flex-col gap-1">
                        <h2 className={TERMINAL_LABEL}>Error output</h2>
                        <Located text={result.stderr} lineCount={lineCount} onGo={goToLine} className={`${TERMINAL_TEXT} text-[#fca5a5]`} />
                      </div>
                    )}
                    {nothingPrinted && <p className="font-mono text-xs text-[var(--vl-editor-dim)]">The program printed nothing.</p>}
                    {noMain && (
                      <p className="text-xs leading-relaxed text-[var(--vl-editor-warm)]">
                        This code has no <code className="font-mono">main</code>, so there is nothing to run yet. Put what you want to
                        try in the <button type="button" onClick={() => showPanel("try")} className="underline underline-offset-2">Try</button> tab
                        (for example a function call), or press Make runnable.
                      </p>
                    )}
                    {result.status !== "ok" && (
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void makeItRunnable()}
                          disabled={fixing || signedIn === false}
                          className="rounded-sm bg-[var(--vl-editor-warm)] px-2.5 py-1 text-xs font-semibold text-[#1e1b4b] hover:bg-[#fef3c7] disabled:opacity-50"
                        >
                          Fix it for me
                        </button>
                        <button
                          type="button"
                          onClick={() => askTutor("Explain this error")}
                          disabled={signedIn === false}
                          className="rounded-sm border border-white/20 px-2.5 py-1 text-xs font-medium hover:bg-white/10 disabled:opacity-50"
                        >
                          Explain the error
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {panelTab === "input" && (
              <div className="flex min-h-0 flex-1 flex-col gap-1.5 px-3 py-2">
                <p className="text-xs text-[var(--vl-editor-dim)]">What the program reads when it asks for input, one value per line.</p>
                <textarea
                  value={stdin}
                  onChange={(event) => setStdin(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                      event.preventDefault();
                      void execute();
                    }
                  }}
                  spellCheck={false}
                  maxLength={10000}
                  aria-label="Program input"
                  placeholder={"5\n3 4"}
                  className="scrollbar-thin min-h-0 w-full flex-1 resize-none rounded-sm border border-white/15 bg-black/20 px-2.5 py-2 font-mono text-xs text-[var(--vl-editor-text)] placeholder:text-[var(--vl-editor-dim)] focus:border-indigo-300 focus:ring-0"
                />
              </div>
            )}

            {panelTab === "try" && tryHelp && (
              <div className="flex min-h-0 flex-1 flex-col gap-1.5 px-3 py-2">
                <p className="text-xs leading-relaxed text-[var(--vl-editor-dim)]">
                  One expression per line, as you would type it in {tryHelp.where}. Each is evaluated after your code and its value
                  shown in Output, so the code needs no main.
                </p>
                <textarea
                  value={tries[language] ?? ""}
                  onChange={(event) => setTries((current) => ({ ...current, [language]: event.target.value }))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                      event.preventDefault();
                      void execute();
                    }
                  }}
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                  maxLength={4000}
                  aria-label="Expressions to try"
                  placeholder={tryHelp.example}
                  className="scrollbar-thin min-h-0 w-full flex-1 resize-none rounded-sm border border-white/15 bg-black/20 px-2.5 py-2 font-mono text-xs text-[var(--vl-editor-text)] [font-variant-ligatures:none] placeholder:text-[var(--vl-editor-dim)] focus:border-indigo-300 focus:ring-0"
                />
              </div>
            )}

            {/* The tutor stays mounted so its conversation survives switching tabs. */}
            <div className={panelTab === "tutor" ? "flex min-h-0 flex-1 flex-col bg-white" : "hidden"}>
              <CodeTutor
                context={tutorContext(language, code, stdin, expressions, result)}
                suggestions={suggestionsFor(result)}
                disabled={signedIn === false}
                question={tutorQuestion}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex flex-none items-center gap-3 whitespace-nowrap border-t border-white/10 bg-[var(--vl-editor-bar)] px-3 py-1 font-mono text-[11px] text-[var(--vl-editor-dim)]">
        <span>
          Ln {cursor.line}, Col {cursor.column}
          {cursor.selected > 0 && ` (${cursor.selected} selected)`}
        </span>
        <span>{languageName}</span>
        {errorCount > 0 && (
          <button type="button" onClick={() => goToLine(diagnostics[0].line)} className="text-[#fca5a5] hover:underline">
            ✕ {errorCount}
          </button>
        )}
        <span className="ml-auto min-w-0 truncate">
          {running ? "Running…" : fixing ? "Fixing…" : result ? `${HEADLINES[result.status]} · ${seconds(result.duration_ms)}` : "Ready"}
        </span>
      </div>
    </div>
  );
}

/**
 * The Code tab's editor: CodeMirror 6, set up the way a desktop IDE behaves.
 * Highlighting as you type, line numbers, the current line marked, matching
 * brackets, auto-indent and closing pairs, Ctrl+/ comments, Ctrl+F search,
 * Alt+↑/↓ to move lines, word completion, real undo, and the compiler's
 * errors marked on their lines.
 *
 * The component owns one EditorView for its lifetime and is controlled the
 * React way: `value` in, `onChange` out. Text set from outside (a handover,
 * "Make runnable", switching language) starts a fresh document with its own
 * undo history; the Code tab offers its own Undo for a fix.
 */

import { autocompletion, closeBrackets, closeBracketsKeymap, completeAnyWord, completionKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab, toggleComment } from "@codemirror/commands";
import { cpp } from "@codemirror/lang-cpp";
import { java } from "@codemirror/lang-java";
import { python } from "@codemirror/lang-python";
import {
  bracketMatching,
  HighlightStyle,
  indentOnInput,
  indentUnit,
  StreamLanguage,
  syntaxHighlighting,
} from "@codemirror/language";
import { haskell } from "@codemirror/legacy-modes/mode/haskell";
import { type Diagnostic as LintDiagnostic, lintGutter, setDiagnostics } from "@codemirror/lint";
import { highlightSelectionMatches, search, searchKeymap } from "@codemirror/search";
import { Compartment, EditorSelection, EditorState, type Extension } from "@codemirror/state";
import {
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import type { CodeLanguage } from "../../shared/handoff";
import type { Diagnostic } from "./diagnostics";

export interface EditorHandle {
  focus: () => void;
  /** Puts the cursor at the start of `line` (1-based), scrolled into view. */
  goToLine: (line: number, column?: number | null) => void;
}

export interface CursorPosition {
  line: number;
  column: number;
  /** Characters selected, 0 when nothing is. */
  selected: number;
}

interface EditorProps {
  value: string;
  language: CodeLanguage;
  fontSize: number;
  diagnostics: Diagnostic[];
  ariaLabel: string;
  onChange: (value: string) => void;
  onRun: () => void;
  onCursor: (position: CursorPosition) => void;
}

const LANGUAGES: Record<CodeLanguage, () => Extension> = {
  haskell: () => StreamLanguage.define(haskell),
  java: () => java(),
  cpp: () => cpp(),
  python: () => python(),
};
// Python and Haskell are indented by convention; four spaces for Python (PEP 8), two elsewhere.
const INDENT: Record<CodeLanguage, string> = { haskell: "  ", java: "    ", cpp: "    ", python: "    " };

// The editor's own colours: the same deep indigo the Code tab has always used.
const highlightStyle = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword, t.definitionKeyword, t.modifier], color: "#c4b5fd" },
  { tag: [t.typeName, t.className, t.namespace, t.standard(t.typeName)], color: "#93c5fd" },
  { tag: [t.function(t.variableName), t.function(t.definition(t.variableName)), t.definition(t.function(t.variableName))], color: "#a5f3fc" },
  { tag: [t.string, t.special(t.string), t.character, t.regexp], color: "#fde68a" },
  { tag: [t.number, t.bool, t.null, t.atom, t.constant(t.variableName), t.standard(t.variableName)], color: "#fdba74" },
  { tag: [t.comment, t.lineComment, t.blockComment, t.docComment], color: "#8b8fd6", fontStyle: "italic" },
  { tag: [t.meta, t.processingInstruction, t.annotation], color: "#f9a8d4" },
  { tag: [t.operator, t.punctuation, t.bracket, t.separator], color: "#c7d2fe" },
  { tag: t.invalid, color: "#fca5a5" },
]);

function themeFor(fontSize: number): Extension {
  return EditorView.theme(
    {
      "&": { height: "100%", fontSize: `${fontSize}px`, backgroundColor: "var(--vl-editor-bg)", color: "var(--vl-editor-text)" },
      ".cm-scroller": {
        fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        // Ligatures turn "->" and "<=" into single glyphs: pretty, but unlike what the student typed.
        fontVariantLigatures: "none",
        lineHeight: "1.55",
        scrollbarWidth: "thin",
      },
      ".cm-content": { caretColor: "var(--vl-editor-warm)", padding: "6px 0" },
      ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--vl-editor-warm)", borderLeftWidth: "2px" },
      "&.cm-focused": { outline: "none" },
      "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
        { backgroundColor: "rgb(129 140 248 / 0.38)" },
      ".cm-activeLine": { backgroundColor: "rgb(255 255 255 / 0.045)" },
      ".cm-gutters": { backgroundColor: "var(--vl-editor-bg)", color: "var(--vl-editor-dim)", border: "none", borderRight: "1px solid rgb(255 255 255 / 0.08)" },
      ".cm-activeLineGutter": { backgroundColor: "rgb(255 255 255 / 0.06)", color: "var(--vl-editor-text)" },
      ".cm-lineNumbers .cm-gutterElement": { padding: "0 6px 0 8px", minWidth: "2.2em" },
      ".cm-matchingBracket": { backgroundColor: "rgb(253 230 138 / 0.18)", outline: "1px solid rgb(253 230 138 / 0.5)", color: "inherit" },
      ".cm-nonmatchingBracket": { backgroundColor: "rgb(252 165 165 / 0.25)" },
      ".cm-selectionMatch": { backgroundColor: "rgb(165 243 252 / 0.14)" },
      ".cm-searchMatch": { backgroundColor: "rgb(253 230 138 / 0.25)" },
      ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "rgb(253 230 138 / 0.5)" },
      ".cm-panels": { backgroundColor: "var(--vl-editor-bar)", color: "var(--vl-editor-text)" },
      ".cm-panels.cm-panels-top": { borderBottom: "1px solid rgb(255 255 255 / 0.1)" },
      ".cm-panel.cm-search": { fontFamily: "Inter, system-ui, sans-serif", fontSize: "12px", padding: "6px 8px" },
      ".cm-panel.cm-search input, .cm-panel.cm-search button": { fontSize: "12px" },
      ".cm-textfield": { backgroundColor: "var(--vl-editor-bg)", color: "var(--vl-editor-text)", border: "1px solid rgb(255 255 255 / 0.2)", borderRadius: "4px" },
      ".cm-button": { backgroundImage: "none", backgroundColor: "rgb(255 255 255 / 0.08)", color: "var(--vl-editor-text)", border: "1px solid rgb(255 255 255 / 0.15)", borderRadius: "4px" },
      ".cm-tooltip": { backgroundColor: "var(--vl-editor-bar)", color: "var(--vl-editor-text)", border: "1px solid rgb(255 255 255 / 0.15)", borderRadius: "6px" },
      ".cm-tooltip-autocomplete > ul > li[aria-selected]": { backgroundColor: "rgb(129 140 248 / 0.45)", color: "#fff" },
      ".cm-diagnostic": { fontFamily: "Inter, system-ui, sans-serif", fontSize: "12px", padding: "4px 8px" },
      ".cm-diagnostic-error": { borderLeft: "3px solid #fca5a5" },
      ".cm-diagnostic-warning": { borderLeft: "3px solid #fde68a" },
      ".cm-lintRange-error": { backgroundImage: "none", textDecoration: "underline wavy #fca5a5", textUnderlineOffset: "3px" },
      ".cm-lintRange-warning": { backgroundImage: "none", textDecoration: "underline wavy #fde68a", textUnderlineOffset: "3px" },
    },
    { dark: true }
  );
}

function toLint(state: EditorState, diagnostics: Diagnostic[]): LintDiagnostic[] {
  return diagnostics
    .filter((item) => item.line <= state.doc.lines)
    .map((item) => {
      const line = state.doc.line(item.line);
      const start = item.column ? Math.min(line.from + item.column - 1, line.to) : line.from;
      // Underline from the column to the end of the word there, or the whole line without one.
      const word = item.column ? state.wordAt(start) : null;
      const end = word ? word.to : line.to;
      return { from: start, to: Math.max(end, start), severity: item.severity, message: item.message, source: "compiler" };
    });
}

export const Editor = forwardRef<EditorHandle, EditorProps>(function Editor(
  { value, language, fontSize, diagnostics, ariaLabel, onChange, onRun, onCursor },
  ref
) {
  const host = useRef<HTMLDivElement | null>(null);
  const view = useRef<EditorView | null>(null);
  const languageSlot = useRef(new Compartment());
  const themeSlot = useRef(new Compartment());
  // The latest callbacks, read by the editor's listeners without rebuilding it.
  const callbacks = useRef({ onChange, onRun, onCursor });
  callbacks.current = { onChange, onRun, onCursor };

  /** A fresh editor state for `doc`: the full setup, with an empty undo history. */
  const createState = (doc: string) =>
    EditorState.create({
      doc,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightSpecialChars(),
        history(),
        drawSelection(),
        dropCursor(),
        EditorState.allowMultipleSelections.of(true),
        indentOnInput(),
        bracketMatching(),
        closeBrackets(),
        autocompletion({ override: [completeAnyWord], activateOnTyping: true, icons: false }),
        rectangularSelection(),
        highlightActiveLine(),
        highlightSelectionMatches(),
        search({ top: true }),
        lintGutter(),
        syntaxHighlighting(highlightStyle),
        EditorState.tabSize.of(4),
        languageSlot.current.of([LANGUAGES[language](), indentUnit.of(INDENT[language])]),
        themeSlot.current.of(themeFor(fontSize)),
        EditorView.contentAttributes.of({ "aria-label": ariaLabel, spellcheck: "false", autocapitalize: "off", autocorrect: "off" }),
        keymap.of([
          { key: "Mod-Enter", run: () => (callbacks.current.onRun(), true), preventDefault: true },
          { key: "Mod-/", run: toggleComment },
          ...closeBracketsKeymap,
          ...defaultKeymap,
          ...searchKeymap,
          ...historyKeymap,
          ...completionKeymap,
          indentWithTab,
        ]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) callbacks.current.onChange(update.state.doc.toString());
          if (update.docChanged || update.selectionSet) {
            const { head, from, to } = update.state.selection.main;
            const line = update.state.doc.lineAt(head);
            callbacks.current.onCursor({ line: line.number, column: head - line.from + 1, selected: to - from });
          }
        }),
      ],
    });

  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({ parent: host.current, state: createState(value) });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // The editor is built once; the effects below keep it in step with the props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Text replaced from outside (a handover, a fix, another language's draft)
  // starts a fresh state, so Ctrl+Z never brings back a different program.
  useEffect(() => {
    const editor = view.current;
    if (!editor || editor.state.doc.toString() === value) return;
    editor.setState(createState(value));
    callbacks.current.onCursor({ line: 1, column: 1, selected: 0 });
    // Only a new value replaces the document; createState reads the other props itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: languageSlot.current.reconfigure([LANGUAGES[language](), indentUnit.of(INDENT[language])]) });
  }, [language]);

  useEffect(() => {
    view.current?.dispatch({ effects: themeSlot.current.reconfigure(themeFor(fontSize)) });
  }, [fontSize]);

  useEffect(() => {
    const editor = view.current;
    if (!editor) return;
    editor.dispatch(setDiagnostics(editor.state, toLint(editor.state, diagnostics)));
  }, [diagnostics]);

  useImperativeHandle(ref, () => ({
    focus: () => view.current?.focus(),
    goToLine: (lineNumber, column) => {
      const editor = view.current;
      if (!editor) return;
      const line = editor.state.doc.line(Math.min(Math.max(1, lineNumber), editor.state.doc.lines));
      const position = column ? Math.min(line.from + column - 1, line.to) : line.from;
      editor.dispatch({ selection: EditorSelection.cursor(position), scrollIntoView: true });
      editor.focus();
    },
  }));

  return <div ref={host} className="h-full min-h-0 overflow-hidden" />;
});

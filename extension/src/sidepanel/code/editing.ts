/**
 * What the Code tab's editor does for the person typing, beyond inserting the
 * key they pressed: keeps and adjusts indentation, closes brackets and
 * quotes, indents and unindents lines, and toggles comments. Each language
 * has its own idea of where a block opens and how a comment starts.
 *
 * Pure: `editFor` looks at the text, the selection and a key, and says what
 * to change (or null to let the browser handle the key). The component
 * applies it (tabs/CodeTab.tsx), so this can be tested without a browser.
 */

import type { CodeLanguage } from "../../shared/handoff";

export interface EditorState {
  value: string;
  /** Selection start and end; equal when nothing is selected. */
  start: number;
  end: number;
}

export interface KeyPress {
  key: string;
  shift: boolean;
  /** Ctrl, or Command on a Mac. */
  mod: boolean;
  alt: boolean;
}

/** Replace `value[from..to)` with `insert`, then select `[selectStart, selectEnd)`. */
export interface Edit {
  from: number;
  to: number;
  insert: string;
  selectStart: number;
  selectEnd: number;
}

interface LanguageRules {
  /** One level of indentation. */
  indent: string;
  comment: string;
  /** The text before the cursor (right-trimmed) ends a line that opens a block. */
  opensBlock: (before: string) => boolean;
  /** Characters closed automatically when typed. */
  pairs: Record<string, string>;
  /** The line (trimmed) ends its block: the next line goes back a level. */
  closesBlock?: (line: string) => boolean;
}

const BRACKETS: Record<string, string> = { "(": ")", "[": "]", "{": "}" };

// A block, an argument list or array carried onto the next line, a `case x:`
// label or an access label, or a lambda arrow.
const opensBraceBlock = (before: string): boolean => /[{([:]$/.test(before) || /->$/.test(before);

const RULES: Record<CodeLanguage, LanguageRules> = {
  java: {
    indent: "  ",
    comment: "//",
    opensBlock: opensBraceBlock,
    pairs: { ...BRACKETS, '"': '"', "'": "'" },
  },
  cpp: {
    indent: "  ",
    comment: "//",
    opensBlock: opensBraceBlock,
    pairs: { ...BRACKETS, '"': '"', "'": "'" },
  },
  python: {
    // Four spaces, as Python's own style guide asks.
    indent: "    ",
    comment: "#",
    // `def f():`, `if x:`, `else:`, or an open bracket carried onto the next line.
    opensBlock: (before) => /[:([{]$/.test(before),
    pairs: { ...BRACKETS, '"': '"', "'": "'" },
    closesBlock: (line) => /^(return|pass|break|continue|raise)\b/.test(line),
  },
  haskell: {
    indent: "  ",
    comment: "--",
    // A definition continued on the next line, or a layout keyword. `==`, `<=`,
    // `>=` and `/=` end in "=" too, but are comparisons, not definitions.
    opensBlock: (before) =>
      /(^|[^=<>/!])=$/.test(before) || /(^|[^\w'])(where|do|of|let|then|else|in)$/.test(before) || /(->|[([])$/.test(before),
    // No single quote: in Haskell it is also part of names (x', foldl').
    pairs: { ...BRACKETS, '"': '"' },
  },
};

function lineStart(value: string, position: number): number {
  return value.lastIndexOf("\n", position - 1) + 1;
}

function lineEnd(value: string, position: number): number {
  const index = value.indexOf("\n", position);
  return index === -1 ? value.length : index;
}

function leadingSpace(line: string): string {
  return /^[ \t]*/.exec(line)?.[0] ?? "";
}

function caret(position: number, from: number, to: number, insert: string): Edit {
  return { from, to, insert, selectStart: position, selectEnd: position };
}

function onEnter(state: EditorState, rules: LanguageRules): Edit {
  const { value, start, end } = state;
  const from = lineStart(value, start);
  const indent = leadingSpace(value.slice(from, start));
  const before = value.slice(from, start).trimEnd();
  const opens = before.length > 0 && rules.opensBlock(before);
  // After `return` and the like (Python), the block is over.
  if (!opens && rules.closesBlock?.(before.trim()) && indent.length >= rules.indent.length) {
    const back = indent.slice(rules.indent.length);
    return caret(start + 1 + back.length, start, end, `\n${back}`);
  }
  const inner = indent + (opens ? rules.indent : "");
  const closer = BRACKETS[before.slice(-1)];
  // Enter between a bracket and its partner: the partner goes on its own line.
  if (opens && closer !== undefined && value[end] === closer) {
    return caret(start + 1 + inner.length, start, end, `\n${inner}\n${indent}`);
  }
  return caret(start + 1 + inner.length, start, end, `\n${inner}`);
}

/** Indents or unindents every line the selection touches. */
function shiftLines(state: EditorState, outdent: boolean, unit: string): Edit | null {
  const { value, start, end } = state;
  const from = lineStart(value, start);
  // A selection that ends at the very start of a line does not include that line.
  const last = end > start && value[end - 1] === "\n" ? end - 1 : end;
  const to = lineEnd(value, last);
  const lines = value.slice(from, to).split("\n");
  const changed = lines.map((line) => {
    if (!outdent) return line.length > 0 ? unit + line : line;
    if (line.startsWith(unit)) return line.slice(unit.length);
    // Less than a full level left: take what there is.
    if (/^ +/.test(line)) return line.replace(/^ +/, "");
    return line.startsWith("\t") || line.startsWith(" ") ? line.slice(1) : line;
  });
  const insert = changed.join("\n");
  if (insert === value.slice(from, to)) return null;
  const firstShift = changed[0].length - lines[0].length;
  return {
    from,
    to,
    insert,
    // A selection grows to whole lines, so Tab can be pressed again.
    selectStart: start === end ? Math.max(from, start + firstShift) : from,
    selectEnd: start === end ? Math.max(from, start + firstShift) : from + insert.length,
  };
}

function toggleComment(state: EditorState, rules: LanguageRules): Edit {
  const { value, start, end } = state;
  const from = lineStart(value, start);
  const last = end > start && value[end - 1] === "\n" ? end - 1 : end;
  const to = lineEnd(value, last);
  const lines = value.slice(from, to).split("\n");
  const written = lines.filter((line) => line.trim().length > 0);
  const allCommented = written.length > 0 && written.every((line) => line.trimStart().startsWith(rules.comment));
  // New comment marks line up at the shallowest indentation of the lines.
  const depth = Math.min(...written.map((line) => leadingSpace(line).length), Number.MAX_SAFE_INTEGER);
  const changed = lines.map((line) => {
    if (line.trim().length === 0) return line;
    if (allCommented) {
      const at = line.indexOf(rules.comment);
      const after = line.slice(at + rules.comment.length);
      return line.slice(0, at) + (after.startsWith(" ") ? after.slice(1) : after);
    }
    return `${line.slice(0, depth)}${rules.comment} ${line.slice(depth)}`;
  });
  const insert = changed.join("\n");
  const shift = changed[0].length - lines[0].length;
  return {
    from,
    to,
    insert,
    selectStart: start === end ? Math.max(from, start + shift) : from,
    selectEnd: start === end ? Math.max(from, start + shift) : from + insert.length,
  };
}

function onBackspace(state: EditorState, rules: LanguageRules): Edit | null {
  const { value, start, end } = state;
  if (start !== end || start === 0) return null;
  // Between a pair typed a moment ago: both go.
  const previous = value[start - 1];
  if (rules.pairs[previous] !== undefined && value[start] === rules.pairs[previous]) {
    return caret(start - 1, start - 1, start + 1, "");
  }
  // In the indentation: back one level, not one space.
  const from = lineStart(value, start);
  const before = value.slice(from, start);
  if (before.length > 0 && /^ +$/.test(before)) {
    const remove = before.length % rules.indent.length || rules.indent.length;
    return caret(start - remove, start - remove, start, "");
  }
  return null;
}

function onCharacter(state: EditorState, key: string, rules: LanguageRules): Edit | null {
  const { value, start, end } = state;
  const next = value[end] ?? "";
  const closes = Object.values(rules.pairs).includes(key);
  // Typing the closing character that is already there steps over it.
  if (closes && start === end && next === key) {
    return caret(start + 1, start, start, "");
  }
  // A closing brace typed on an otherwise empty line comes back one level.
  if (key === "}" && start === end) {
    const from = lineStart(value, start);
    const before = value.slice(from, start);
    if (before.length >= rules.indent.length && /^ +$/.test(before)) {
      return caret(start - rules.indent.length + 1, start - rules.indent.length, start, "}");
    }
  }
  const partner = rules.pairs[key];
  if (partner === undefined) return null;
  if (start !== end) {
    // Wrap what is selected.
    return { from: start, to: end, insert: key + value.slice(start, end) + partner, selectStart: start + 1, selectEnd: end + 1 };
  }
  const isQuote = key === partner;
  const previous = value[start - 1] ?? "";
  // A quote right after a letter, digit or backslash is an apostrophe or an escape, not an opening quote.
  if (isQuote && /[\w\\]/.test(previous)) return null;
  // Only close when what follows would not end up glued to the new partner.
  if (next !== "" && !/[\s)\]},;]/.test(next)) return null;
  return caret(start + 1, start, end, key + partner);
}

/** The change a key press makes, or null to leave the key to the browser. */
export function editFor(state: EditorState, press: KeyPress, language: CodeLanguage): Edit | null {
  const rules = RULES[language];
  if (press.alt) return null;
  if (press.mod) return press.key === "/" ? toggleComment(state, rules) : null;
  if (press.key === "Enter") return press.shift ? null : onEnter(state, rules);
  if (press.key === "Tab") {
    const multiline = state.value.slice(state.start, state.end).includes("\n");
    if (press.shift || multiline) return shiftLines(state, press.shift, rules.indent);
    const column = state.start - lineStart(state.value, state.start);
    const spaces = rules.indent.length - (column % rules.indent.length);
    return caret(state.start + spaces, state.start, state.end, " ".repeat(spaces));
  }
  if (press.key === "Backspace") return onBackspace(state, rules);
  if (press.key.length === 1) return onCharacter(state, press.key, rules);
  return null;
}

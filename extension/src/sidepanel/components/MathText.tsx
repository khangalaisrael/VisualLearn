/**
 * Renders text containing inline/block LaTeX math and fenced code blocks
 * alongside plain text. Chat answers and equation objects both mix prose
 * with LaTeX (delimited as $$...$$, \[...\], $...$, or \(...\) — the model
 * isn't told which style to use, so all four are recognized), so this is
 * shared rather than duplicated between AskTab's object cards and its chat
 * bubbles. Chat answers can also contain ``` fenced code blocks (see
 * prompts/chat_figure.v5.md / chat_slide.v5.md), rendered via CodeBlock.
 *
 * Outside code, text also gets light formatting: **bold** and *italic* spans,
 * `#`/`##`/`###` headings, `- `/`* ` bullet lists, `1.` numbered lists, pipe
 * tables (components/markdownTable.ts), and line breaks. A heading, a list item or a bold span may contain math. This
 * is a small pass over lines, not a full markdown parser, kept in-repo
 * rather than pulling in a markdown dependency for a narrow need.
 */

import katex from "katex";
import { Fragment, type ReactNode, useMemo } from "react";

import { CodeBlock } from "./CodeBlock";
import { alignments, isSeparatorRow, looksLikeRow, splitCells } from "./markdownTable";

interface Segment {
  // "code" is a fenced block; "inline" is `code` inside a sentence.
  kind: "text" | "math" | "code" | "inline";
  content: string;
  displayMode: boolean;
  language?: string;
}

const MATH_PATTERN = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;

function splitMathSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(MATH_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push({ kind: "text", content: text.slice(lastIndex, index), displayMode: false });
    }
    const [, blockDollar, blockBracket, inlineDollar, inlineParen] = match;
    const isBlock = blockDollar !== undefined || blockBracket !== undefined;
    const latex = blockDollar ?? blockBracket ?? inlineDollar ?? inlineParen ?? "";
    segments.push({ kind: "math", content: latex, displayMode: isBlock });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ kind: "text", content: text.slice(lastIndex), displayMode: false });
  }
  return segments;
}

// Carved out before math splitting runs, so `$`/`\(`/etc. characters
// appearing inside a code fence (e.g. shell prompts, regex literals) are
// never mistaken for LaTeX delimiters — code segments are extracted first,
// and the math pass only ever sees what's left over.
const CODE_FENCE_PATTERN = /```(\w*)\n?([\s\S]*?)```/g;

// `name` inside a sentence. Also carved out before math, for the same
// reason: `$PATH` or `a $ b` in code is not a formula. Both backticks must
// be on one line, so a stray one never swallows the rest of the answer.
const INLINE_CODE_PATTERN = /`([^`\n]+)`/g;

function splitInlineCode(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(INLINE_CODE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) segments.push(...splitMathSegments(text.slice(lastIndex, index)));
    segments.push({ kind: "inline", content: match[1], displayMode: false });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) segments.push(...splitMathSegments(text.slice(lastIndex)));
  return segments;
}

function splitSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CODE_FENCE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push(...splitInlineCode(text.slice(lastIndex, index)));
    }
    const [, language, code] = match;
    segments.push({
      kind: "code",
      content: code.replace(/\n$/, ""),
      displayMode: false,
      language: language || undefined,
    });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push(...splitInlineCode(text.slice(lastIndex)));
  }
  return segments;
}

const HEADING_PATTERN = /^(#{1,6})\s+(.*)$/;
const BULLET_PATTERN = /^\s*[-*]\s+(.*)$/;
const NUMBERED_PATTERN = /^\s*(\d+)[.)]\s+(.*)$/;

const HEADING_CLASSES = [
  "mt-3 block text-base font-semibold text-slate-800 first:mt-0",
  "mt-3 block text-sm font-semibold text-slate-800 first:mt-0",
  "mt-2 block text-sm font-semibold text-slate-700 first:mt-0",
] as const;

/** One piece of a line: plain text (which may hold ** markers), a formula, or `code`. */
type Token =
  | { kind: "text"; text: string }
  | { kind: "math"; latex: string; displayMode: boolean }
  | { kind: "code"; code: string };

/** A run of prose as lines of tokens, or a fenced code block. */
type Block = { kind: "prose"; lines: Token[][] } | { kind: "code"; code: string; language?: string };

/**
 * Regroups the flat text/math/code segments into lines. A formula stays on
 * the line it was written in, so a heading or a list item that contains math
 * is still recognised as one (splitting math out first used to push the
 * formula of "- a variable $x$" onto a line of its own, outside the list).
 */
function toBlocks(segments: Segment[]): Block[] {
  const blocks: Block[] = [];
  let lines: Token[][] | null = null;
  for (const segment of segments) {
    if (segment.kind === "code") {
      lines = null;
      blocks.push({ kind: "code", code: segment.content, language: segment.language });
      continue;
    }
    if (lines === null) {
      lines = [[]];
      blocks.push({ kind: "prose", lines });
    }
    const current: Token[][] = lines;
    if (segment.kind === "math") {
      current[current.length - 1].push({ kind: "math", latex: segment.content, displayMode: segment.displayMode });
      continue;
    }
    if (segment.kind === "inline") {
      current[current.length - 1].push({ kind: "code", code: segment.content });
      continue;
    }
    segment.content.split("\n").forEach((part, index) => {
      if (index > 0) current.push([]);
      if (part.length > 0) current[current.length - 1].push({ kind: "text", text: part });
    });
  }
  return blocks;
}

function KatexSpan({ latex, displayMode }: { latex: string; displayMode: boolean }): JSX.Element {
  const html = useMemo(() => {
    try {
      return katex.renderToString(latex, { displayMode, throwOnError: false });
    } catch {
      return null;
    }
  }, [latex, displayMode]);

  if (html === null) {
    // Malformed LaTeX from the model — show the raw source rather than
    // nothing, so the user isn't left with a silent gap.
    return <code className="font-mono text-slate-600">{latex}</code>;
  }
  // eslint-disable-next-line react/no-danger -- katex.renderToString output, not user/model-controlled HTML
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

// *emphasis*: an asterisk that opens a word and one that closes a word, on the
// same line. "2 * 3 * 4" and "a*b*c" are left alone: there the asterisks have
// a space inside them or a letter or digit outside them.
const ITALIC_PATTERN = /(^|[^*\w])\*(?=\S)([^*\n]*?\S)\*(?![*\w])/g;

/** A stretch of plain text as nodes, with *emphasis* turned into italics. */
function renderText(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let count = 0;
  for (const match of text.matchAll(ITALIC_PATTERN)) {
    const start = (match.index ?? 0) + match[1].length;
    if (start > lastIndex) nodes.push(text.slice(lastIndex, start));
    nodes.push(<em key={`${keyPrefix}-i${count++}`}>{match[2]}</em>);
    lastIndex = (match.index ?? 0) + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

/** The tokens of one line as nodes, with **bold** applied across text and formulas alike. */
function renderInline(tokens: Token[], keyPrefix: string): ReactNode[] {
  const markers = tokens.reduce(
    (count, token) => (token.kind === "text" ? count + token.text.split("**").length - 1 : count),
    0
  );
  // An odd number of markers means one is a literal "**": leave the line as written.
  const applyBold = markers > 0 && markers % 2 === 0;

  const nodes: ReactNode[] = [];
  let bold: ReactNode[] | null = null;
  let key = 0;

  for (const token of tokens) {
    if (token.kind === "math") {
      const formula = <KatexSpan key={`${keyPrefix}-m${key++}`} latex={token.latex} displayMode={token.displayMode} />;
      (bold ?? nodes).push(formula);
      continue;
    }
    if (token.kind === "code") {
      (bold ?? nodes).push(
        <code
          key={`${keyPrefix}-c${key++}`}
          className="rounded-sm bg-slate-100 px-1 py-0.5 font-mono text-[0.92em] text-slate-800"
        >
          {token.code}
        </code>
      );
      continue;
    }
    if (!applyBold) {
      nodes.push(...renderText(token.text, `${keyPrefix}-t${key++}`));
      continue;
    }
    const parts = token.text.split("**");
    for (let index = 0; index < parts.length; index++) {
      if (index > 0) {
        if (bold === null) {
          bold = [];
        } else {
          nodes.push(<strong key={`${keyPrefix}-b${key++}`}>{bold}</strong>);
          bold = null;
        }
      }
      if (parts[index].length > 0) (bold ?? nodes).push(...renderText(parts[index], `${keyPrefix}-t${key++}`));
    }
  }
  return nodes;
}

/** If the line starts with text matching `pattern`: the match, and the line
 * with that leading text replaced by the pattern's last group. */
function matchLine(line: Token[], pattern: RegExp): { match: RegExpExecArray; rest: Token[] } | null {
  const first = line[0];
  if (first === undefined || first.kind !== "text") return null;
  const match = pattern.exec(first.text);
  if (!match) return null;
  const remainder = match[match.length - 1];
  return { match, rest: remainder.length > 0 ? [{ kind: "text", text: remainder }, ...line.slice(1)] : line.slice(1) };
}

/** How a line lays out: running text, a block of its own, or blank. Past either end counts as blank. */
function lineKind(lines: Token[][], index: number): "inline" | "block" | "empty" {
  const line = lines[index];
  if (line === undefined || line.length === 0) return "empty";
  if (line.length === 1 && line[0].kind === "math" && line[0].displayMode) return "block";
  if (matchLine(line, HEADING_PATTERN) || matchLine(line, BULLET_PATTERN) || matchLine(line, NUMBERED_PATTERN)) return "block";
  if (looksLikeRow(line) && index + 1 < lines.length && isSeparatorRow(lines[index + 1])) return "block";
  return "inline";
}

interface OpenList {
  ordered: boolean;
  start: number;
  items: Token[][];
}

function renderProse(lines: Token[][], keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let list: OpenList | null = null;

  const closeList = (open: OpenList) => {
    const key = `${keyPrefix}-list${nodes.length}`;
    const items = open.items.map((item, i) => <li key={i}>{renderInline(item, `${key}-${i}`)}</li>);
    nodes.push(
      open.ordered ? (
        <ol key={key} start={open.start} className="my-1 list-decimal pl-5">
          {items}
        </ol>
      ) : (
        <ul key={key} className="my-1 list-disc pl-5">
          {items}
        </ul>
      )
    );
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // A pipe table: a header row, the --- row under it, then its body rows.
    if (looksLikeRow(line) && i + 1 < lines.length && isSeparatorRow(lines[i + 1])) {
      if (list !== null) {
        closeList(list);
        list = null;
      }
      const align = alignments(lines[i + 1]);
      const header = splitCells(line);
      const body: Token[][][] = [];
      let next = i + 2;
      while (next < lines.length && lines[next].length > 0 && looksLikeRow(lines[next])) {
        body.push(splitCells(lines[next]));
        next++;
      }
      const key = `${keyPrefix}-table${i}`;
      const columns = Math.max(header.length, ...body.map((row) => row.length));
      const cell = (cells: Token[][], column: number, rowKey: string) => (
        <>{renderInline(cells[column] ?? [], `${rowKey}-${column}`)}</>
      );
      nodes.push(
        <div key={key} className="my-1.5 overflow-x-auto">
          <table className="w-full border-collapse text-[0.92em]">
            <thead>
              <tr>
                {Array.from({ length: columns }, (_, column) => (
                  <th
                    key={column}
                    style={{ textAlign: align[column] ?? "left" }}
                    className="border border-slate-200 bg-slate-50 px-2 py-1 font-semibold text-slate-700"
                  >
                    {cell(header, column, `${key}-h`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {Array.from({ length: columns }, (_, column) => (
                    <td key={column} style={{ textAlign: align[column] ?? "left" }} className="border border-slate-200 px-2 py-1 align-top">
                      {cell(row, column, `${key}-r${rowIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = next - 1;
      continue;
    }

    const heading = matchLine(line, HEADING_PATTERN);
    const bullet = heading ? null : matchLine(line, BULLET_PATTERN);
    const numbered = heading || bullet ? null : matchLine(line, NUMBERED_PATTERN);
    const item = bullet ?? numbered;

    if (item) {
      const ordered = numbered !== null;
      if (list !== null && list.ordered !== ordered) {
        closeList(list);
        list = null;
      }
      if (list === null) list = { ordered, start: numbered ? Number(numbered.match[1]) : 1, items: [] };
      list.items.push(item.rest);
      continue;
    }
    if (list !== null) {
      closeList(list);
      list = null;
    }
    if (heading) {
      const level = heading.match[1].length;
      const HeadingTag = (level === 1 ? "h1" : level === 2 ? "h2" : "h3") as "h1" | "h2" | "h3";
      nodes.push(
        <HeadingTag key={`${keyPrefix}-h${i}`} className={HEADING_CLASSES[Math.min(level, 3) - 1]}>
          {renderInline(heading.rest, `${keyPrefix}-h${i}`)}
        </HeadingTag>
      );
      continue;
    }
    if (line.length > 0) {
      nodes.push(<Fragment key={`${keyPrefix}-l${i}`}>{renderInline(line, `${keyPrefix}-l${i}`)}</Fragment>);
      // A line break only between two lines of running text: headings, lists,
      // tables and formulas on their own line are blocks with their own spacing.
      if (lineKind(lines, i) === "inline" && lineKind(lines, i + 1) === "inline") {
        nodes.push(<br key={`${keyPrefix}-br${i}`} />);
      }
    } else if (lineKind(lines, i - 1) === "inline" && lineKind(lines, i + 1) === "inline") {
      // A blank line between paragraphs: a paragraph gap, smaller than a whole empty line.
      nodes.push(<span key={`${keyPrefix}-p${i}`} className="block h-2.5" aria-hidden="true" />);
    }
  }
  if (list !== null) closeList(list);

  return nodes;
}

export function MathText({ text }: { text: string }): JSX.Element {
  const blocks = useMemo(() => toBlocks(splitSegments(text)), [text]);

  return (
    <>
      {blocks.map((block, index) => (
        <Fragment key={index}>
          {block.kind === "code" ? (
            <CodeBlock code={block.code} language={block.language} />
          ) : (
            renderProse(block.lines, `t${index}`)
          )}
        </Fragment>
      ))}
    </>
  );
}

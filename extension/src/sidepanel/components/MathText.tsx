/**
 * Renders text containing inline/block LaTeX math and fenced code blocks
 * alongside plain text. Chat answers and equation objects both mix prose
 * with LaTeX (delimited as $$...$$, \[...\], $...$, or \(...\) — the model
 * isn't told which style to use, so all four are recognized), so this is
 * shared rather than duplicated between AskTab's object cards and its chat
 * bubbles. Chat answers can also contain ``` fenced code blocks (see
 * prompts/chat_figure.v5.md / chat_slide.v5.md), rendered via CodeBlock.
 *
 * Outside code, text also gets light formatting: **bold** spans,
 * `#`/`##`/`###` headings, `- `/`* ` bullet lists, `1.` numbered lists, and
 * line breaks. A heading, a list item or a bold span may contain math. This
 * is a small pass over lines, not a full markdown parser, kept in-repo
 * rather than pulling in a markdown dependency for a narrow need.
 */

import katex from "katex";
import { Fragment, type ReactNode, useMemo } from "react";

import { CodeBlock } from "./CodeBlock";

interface Segment {
  kind: "text" | "math" | "code";
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

function splitSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CODE_FENCE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push(...splitMathSegments(text.slice(lastIndex, index)));
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
    segments.push(...splitMathSegments(text.slice(lastIndex)));
  }
  return segments;
}

const HEADING_PATTERN = /^(#{1,6})\s+(.*)$/;
const BULLET_PATTERN = /^\s*[-*]\s+(.*)$/;
const NUMBERED_PATTERN = /^\s*(\d+)[.)]\s+(.*)$/;

const HEADING_CLASSES = [
  "block text-base font-semibold text-slate-800",
  "block text-sm font-semibold text-slate-800",
  "block text-sm font-semibold text-slate-700",
] as const;

/** One piece of a line: plain text (which may hold ** markers) or a formula. */
type Token = { kind: "text"; text: string } | { kind: "math"; latex: string; displayMode: boolean };

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
    if (!applyBold) {
      nodes.push(token.text);
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
      if (parts[index].length > 0) (bold ?? nodes).push(parts[index]);
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
        <ol key={key} start={open.start} className="list-decimal pl-5">
          {items}
        </ol>
      ) : (
        <ul key={key} className="list-disc pl-5">
          {items}
        </ul>
      )
    );
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
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
    }
    if (i < lines.length - 1) {
      nodes.push(<br key={`${keyPrefix}-br${i}`} />);
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

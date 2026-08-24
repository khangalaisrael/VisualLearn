/**
 * Renders text containing inline/block LaTeX math alongside plain text.
 * Chat answers and equation objects both mix prose with LaTeX (delimited
 * as $$...$$, \[...\], $...$, or \(...\) — the model isn't told which
 * style to use, so all four are recognized), so this is shared rather
 * than duplicated between AskTab's object cards and its chat bubbles.
 *
 * Non-math text segments also get light formatting for **bold** spans,
 * `#`/`##`/`###` headings, `- `/`* ` bullet lists, `1. ` numbered lists,
 * and paragraph breaks — chat answers commonly use these (more so since
 * prompts/chat_slide.v4.md dropped the old fixed 5-section template in
 * favor of adaptive, teacher-style answers) and rendering them as one raw
 * blob was hard to read. This is a small regex pass, not a full markdown
 * parser, kept in-repo rather than pulling in a markdown dependency for a
 * narrow need.
 */

import katex from "katex";
import { Fragment, type ReactNode, useMemo } from "react";

interface Segment {
  kind: "text" | "math";
  content: string;
  displayMode: boolean;
}

const MATH_PATTERN = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;

function splitSegments(text: string): Segment[] {
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

const BOLD_PATTERN = /\*\*([^*]+)\*\*/g;

function renderBold(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let count = 0;
  for (const match of text.matchAll(BOLD_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      nodes.push(text.slice(lastIndex, index));
    }
    nodes.push(<strong key={`${keyPrefix}-b${count++}`}>{match[1]}</strong>);
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

/**
 * Renders one line/paragraph's raw text with both math and bold handled
 * together, so inline math (`the value $x^2$ here`) stays inside the same
 * paragraph instead of splitting it — math extraction has to happen
 * per-block, not once over the whole message, or a mid-paragraph formula
 * would land between two separate `<p>` tags.
 */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const segments = splitSegments(text);
  return segments.flatMap((segment, i) =>
    segment.kind === "math" ? (
      <KatexSpan key={`${keyPrefix}-m${i}`} latex={segment.content} displayMode={segment.displayMode} />
    ) : (
      renderBold(segment.content, `${keyPrefix}-t${i}`)
    )
  );
}

const HEADING_STYLES: Record<number, string> = {
  1: "text-[15px] font-semibold text-indigo-700",
  2: "text-sm font-semibold text-indigo-700",
  3: "text-sm font-semibold text-indigo-600",
};

const HEADING_PATTERN = /^(#{1,3})\s+(.*)/;
const BULLET_PATTERN = /^[-*]\s+(.*)/;
const NUMBERED_PATTERN = /^\d+\.\s+(.*)/;

type RunType = "heading1" | "heading2" | "heading3" | "bullet" | "numbered" | "para";

function classifyLine(line: string): { type: RunType; content: string } | null {
  if (line.trim().length === 0) return null;
  const heading = HEADING_PATTERN.exec(line);
  if (heading) return { type: `heading${heading[1].length}` as RunType, content: heading[2] };
  const bullet = BULLET_PATTERN.exec(line);
  if (bullet) return { type: "bullet", content: bullet[1] };
  const numbered = NUMBERED_PATTERN.exec(line);
  if (numbered) return { type: "numbered", content: numbered[1] };
  return { type: "para", content: line };
}

function renderRun(type: RunType, lines: string[], key: string): ReactNode {
  if (type === "bullet") {
    return (
      <ul key={key} className="list-disc pl-5">
        {lines.map((line, i) => (
          <li key={i}>{renderInline(line, `${key}-${i}`)}</li>
        ))}
      </ul>
    );
  }
  if (type === "numbered") {
    return (
      <ol key={key} className="list-decimal pl-5">
        {lines.map((line, i) => (
          <li key={i}>{renderInline(line, `${key}-${i}`)}</li>
        ))}
      </ol>
    );
  }
  if (type === "heading1" || type === "heading2" || type === "heading3") {
    const level = Number(type.slice(-1));
    return (
      <p key={key} className={HEADING_STYLES[level]}>
        {renderInline(lines[0], key)}
      </p>
    );
  }
  return (
    <p key={key}>
      {lines.map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {renderInline(line, `${key}-${i}`)}
        </Fragment>
      ))}
    </p>
  );
}

/**
 * Groups consecutive same-type lines (a run of bullets, a run of numbered
 * items, consecutive plain prose lines) into one block element each — a
 * blank line or a type change ends the current run. Headings always end
 * their own run immediately: models routinely write `### Heading` with
 * no blank line before the following paragraph/list (unlike the old
 * "heading must be alone in its blank-line-separated block" approach,
 * which left the heading marker unrecognized and printed as literal
 * `###` text whenever that happened).
 */
function renderTextBlock(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const classifiedLines = text.split("\n").map(classifyLine);
  let runType: RunType | null = null;
  let runLines: string[] = [];
  let runIndex = 0;

  const flush = () => {
    if (runType !== null && runLines.length > 0) {
      nodes.push(renderRun(runType, runLines, `${keyPrefix}-r${runIndex++}`));
    }
    runType = null;
    runLines = [];
  };

  for (let i = 0; i < classifiedLines.length; i++) {
    const classified = classifiedLines[i];
    if (classified === null) {
      // A blank line only ends a bullet/numbered run if it isn't just
      // separating loosely-formatted items of the same list — models
      // routinely put a blank line between numbered items for
      // readability, and treating that as a hard break would restart
      // each item as its own single-item <ol> (1, 1, 1 instead of 1, 2,
      // 3, since list-decimal numbering is scoped per <ol>).
      if (runType === "bullet" || runType === "numbered") {
        const next = classifiedLines.slice(i + 1).find((c) => c !== null) ?? null;
        if (next && next.type === runType) continue;
      }
      flush();
      continue;
    }
    const isHeading = classified.type.startsWith("heading");
    if (isHeading) {
      flush();
      runType = classified.type;
      runLines = [classified.content];
      flush();
      continue;
    }
    if (runType !== null && runType !== classified.type) {
      flush();
    }
    runType = classified.type;
    runLines.push(classified.content);
  }
  flush();

  return nodes;
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

export function MathText({ text }: { text: string }): JSX.Element {
  const blocks = useMemo(() => renderTextBlock(text, "t"), [text]);
  // `space-y` rather than per-block margin so a single-block caller (a
  // table cell, an equation display) gets zero extra spacing — it only
  // takes effect between siblings, i.e. multi-paragraph chat answers.
  return <div className="space-y-2">{blocks}</div>;
}

/**
 * Renders text containing inline/block LaTeX math alongside plain text.
 * Chat answers and equation objects both mix prose with LaTeX (delimited
 * as $$...$$, \[...\], $...$, or \(...\) — the model isn't told which
 * style to use, so all four are recognized), so this is shared rather
 * than duplicated between AskTab's object cards and its chat bubbles.
 *
 * Non-math text segments also get light formatting for **bold** spans,
 * `- `/`* ` bullet lists, and line breaks — chat answers commonly use
 * these and rendering them as one raw blob was hard to read. This is a
 * small regex pass, not a full markdown parser, kept in-repo rather than
 * pulling in a markdown dependency for a narrow need.
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

function renderInline(text: string, keyPrefix: string): ReactNode[] {
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

function renderTextBlock(text: string, keyPrefix: string): ReactNode[] {
  const lines = text.split("\n");
  const nodes: ReactNode[] = [];
  let bulletLines: string[] = [];

  const flushBullets = () => {
    if (bulletLines.length === 0) return;
    nodes.push(
      <ul key={`${keyPrefix}-ul${nodes.length}`} className="list-disc pl-5">
        {bulletLines.map((line, i) => (
          <li key={i}>{renderInline(line, `${keyPrefix}-ul${nodes.length}-${i}`)}</li>
        ))}
      </ul>
    );
    bulletLines = [];
  };

  lines.forEach((line, i) => {
    const bulletMatch = /^[-*]\s+(.*)/.exec(line);
    if (bulletMatch) {
      bulletLines.push(bulletMatch[1]);
      return;
    }
    flushBullets();
    if (line.length > 0) {
      nodes.push(<Fragment key={`${keyPrefix}-l${i}`}>{renderInline(line, `${keyPrefix}-l${i}`)}</Fragment>);
    }
    if (i < lines.length - 1) {
      nodes.push(<br key={`${keyPrefix}-br${i}`} />);
    }
  });
  flushBullets();

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
  const segments = useMemo(() => splitSegments(text), [text]);

  return (
    <>
      {segments.map((segment, index) => (
        <Fragment key={index}>
          {segment.kind === "math" ? (
            <KatexSpan latex={segment.content} displayMode={segment.displayMode} />
          ) : (
            renderTextBlock(segment.content, `t${index}`)
          )}
        </Fragment>
      ))}
    </>
  );
}

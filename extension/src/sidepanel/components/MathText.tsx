/**
 * Renders text containing inline/block LaTeX math alongside plain text.
 * Chat answers and equation objects both mix prose with LaTeX (delimited
 * as $$...$$, \[...\], $...$, or \(...\) — the model isn't told which
 * style to use, so all four are recognized), so this is shared rather
 * than duplicated between AskTab's object cards and its chat bubbles.
 */

import katex from "katex";
import { Fragment, useMemo } from "react";

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
            segment.content
          )}
        </Fragment>
      ))}
    </>
  );
}

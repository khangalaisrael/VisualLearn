/**
 * Syntax-highlighted code block — the "code" counterpart to MathText.tsx's
 * KaTeX rendering. Self-hosted via highlight.js's core build (extension
 * pages run under a strict CSP that blocks remote CDN loads, same reason
 * KaTeX is bundled rather than linked — see index.css's theme import), with
 * only a curated set of languages registered rather than the full
 * all-languages bundle.
 *
 * Used both for `type: "code"` slide objects (ObjectCard.tsx) and for
 * fenced ``` blocks inside chat answers (MathText.tsx).
 */

import { useState } from "react";

import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";

import { Button } from "./Button";

const REGISTERED_LANGUAGES = [
  "python",
  "javascript",
  "typescript",
  "java",
  "c",
  "cpp",
  "csharp",
  "sql",
  "bash",
  "json",
];

hljs.registerLanguage("python", python);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("java", java);
hljs.registerLanguage("c", c);
hljs.registerLanguage("cpp", cpp);
hljs.registerLanguage("csharp", csharp);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("json", json);

interface CodeBlockProps {
  code: string;
  language?: string | null;
}

function highlight(code: string, language?: string | null): { html: string; language: string | null } {
  const normalized = language?.toLowerCase().trim();
  if (normalized && hljs.getLanguage(normalized)) {
    const result = hljs.highlight(code, { language: normalized });
    return { html: result.value, language: normalized };
  }
  // No language given (or one we don't recognize) — auto-detect among the
  // languages actually registered above, rather than guessing at plain text.
  const auto = hljs.highlightAuto(code, REGISTERED_LANGUAGES);
  return { html: auto.value, language: auto.language ?? null };
}

export function CodeBlock({ code, language }: CodeBlockProps): JSX.Element {
  const [copied, setCopied] = useState(false);
  const { html, language: detected } = highlight(code, language);

  const copy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="overflow-hidden rounded-sm border border-slate-200 bg-slate-50">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-100/80 px-3 py-1">
        <span className="font-mono text-[11px] uppercase tracking-wide text-slate-500">{detected ?? "code"}</span>
        <Button variant="secondary" className="px-2 py-0.5 text-xs" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto px-3 py-2">
        {/* eslint-disable-next-line react/no-danger -- hljs.highlight's own output, not user-supplied HTML */}
        <code className="font-mono text-xs" dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}

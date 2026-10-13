/**
 * Where a compiler or a traceback says the problem is, so the Code tab can
 * mark the line in the editor and let the student jump to it.
 *
 * Pure: reads the text the sandbox returned (compiler output, then error
 * output) and lists the lines it names in the student's file. The sandbox
 * names the file itself (prog.hs, prog.cc, prog.java, prog.py), so any file
 * name is accepted. Lines past the end of the student's code are dropped:
 * those are in the main the runner wrote around expressions to try.
 */

export interface Diagnostic {
  /** 1-based line in the student's code. */
  line: number;
  /** 1-based column, when the compiler gave one. */
  column: number | null;
  severity: "error" | "warning";
  /** The message, trimmed to its first line. */
  message: string;
}

// prog.hs:3:7: error: ...   prog.cc:5:3: warning: ...   prog.java:4: error: ...
const COMPILER = /^[^\s:]+\.(?:hs|lhs|cc|cpp|cxx|c|h|hpp|java|py):(\d+)(?::(\d+))?(?:-\d+)?:\s*(?:(error|warning|fatal error):?(?:\s*\[[^\]]*\])?:?)?\s*(.*)$/i;
// GHC also writes a range: prog.hs:(3,1)-(4,10): error:
const GHC_RANGE = /^[^\s:]+\.l?hs:\((\d+),(\d+)\)-\(\d+,\d+\):\s*(?:(error|warning):?(?:\s*\[[^\]]*\])?:?)?\s*(.*)$/i;
//   File "prog.py", line 5, in <module>
const PYTHON = /^\s*File "[^"]*", line (\d+)/;

function firstLine(text: string): string {
  return text.split("\n")[0].trim();
}

export function parseDiagnostics(output: string, lineCount: number): Diagnostic[] {
  const lines = output.split("\n");
  const found: Diagnostic[] = [];
  let pythonLine: number | null = null;

  lines.forEach((raw, index) => {
    const text = raw.trimEnd();
    const range = GHC_RANGE.exec(text);
    const compiler = range ?? COMPILER.exec(text);
    if (compiler) {
      const [, line, column, kind, rest] = compiler;
      // GHC puts the message on the following, indented lines.
      const message = firstLine(rest || lines[index + 1]?.trim() || "");
      found.push({
        line: Number(line),
        column: column ? Number(column) : null,
        severity: kind && /warning/i.test(kind) ? "warning" : "error",
        message,
      });
      return;
    }
    const python = PYTHON.exec(text);
    if (python) pythonLine = Number(python[1]);
  });

  // A traceback lists every frame; the last one in the file is where it failed,
  // and the exception itself is the traceback's last line.
  if (pythonLine !== null) {
    const exception = lines.map((line) => line.trim()).filter(Boolean).at(-1) ?? "";
    found.push({ line: pythonLine, column: null, severity: "error", message: exception });
  }

  const seen = new Set<string>();
  return found.filter((item) => {
    const key = `${item.line}:${item.column}:${item.message}`;
    if (item.line < 1 || item.line > lineCount || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Splits output text into plain runs and the `file:line` / `line N` places it names. */
export function linkLocations(text: string, lineCount: number): ({ text: string } | { text: string; line: number })[] {
  const parts: ({ text: string } | { text: string; line: number })[] = [];
  const pattern = /([^\s:"]+\.(?:hs|lhs|cc|cpp|cxx|c|h|hpp|java|py):(\d+)(?::\d+)?)|(line (\d+))/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const line = Number(match[2] ?? match[4]);
    if (line < 1 || line > lineCount) continue;
    const start = match.index ?? 0;
    if (start > last) parts.push({ text: text.slice(last, start) });
    parts.push({ text: match[0], line });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

/**
 * Markdown tables for MathText: recognising the rows of a pipe table and
 * splitting each row into cells. Cells may hold formulas and inline code
 * (other token kinds), so only plain text is split on `|`; a `|` inside a
 * formula such as $|x|$ or inside `code` never starts a new cell.
 *
 * Pure, over any token type whose text pieces look like { kind: "text" }.
 */

export type TextToken = { kind: "text"; text: string };

/** The line's leading text, when the line is all text (separator rows always are). */
function plainText<T extends { kind: string }>(line: T[]): string | null {
  return line.every((token) => token.kind === "text") ? line.map((token) => (token as unknown as TextToken).text).join("") : null;
}

/** `| --- | :---: |` and `---|---`: the row under a table's header. */
export function isSeparatorRow<T extends { kind: string }>(line: T[]): boolean {
  const text = plainText(line);
  if (text === null) return false;
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(text) || /^\s*\|\s*:?-{3,}:?\s*\|\s*$/.test(text);
}

/** A line that can be a table row: it has a `|` in its text. */
export function looksLikeRow<T extends { kind: string }>(line: T[]): boolean {
  return line.some((token) => token.kind === "text" && (token as unknown as TextToken).text.includes("|"));
}

/** The cells of one row, each a list of tokens, with the outer pipes and the spaces around cells removed. */
export function splitCells<T extends { kind: string }>(line: T[]): T[][] {
  const cells: T[][] = [[]];
  for (const token of line) {
    if (token.kind !== "text") {
      cells[cells.length - 1].push(token);
      continue;
    }
    const pieces = (token as unknown as TextToken).text.split(/(?<!\\)\|/);
    pieces.forEach((piece, index) => {
      if (index > 0) cells.push([]);
      const text = piece.replace(/\\\|/g, "|");
      if (text.length > 0) cells[cells.length - 1].push({ ...token, text } as T);
    });
  }
  const trimmed = cells.map((cell) => trimCell(cell));
  // "| a | b |" has an empty cell before the first pipe and after the last.
  if (trimmed.length > 1 && trimmed[0].length === 0) trimmed.shift();
  if (trimmed.length > 1 && trimmed[trimmed.length - 1].length === 0) trimmed.pop();
  return trimmed;
}

function trimCell<T extends { kind: string }>(cell: T[]): T[] {
  const out = [...cell];
  const first = out[0] as unknown as TextToken | undefined;
  if (first?.kind === "text") {
    const text = first.text.trimStart();
    if (text) out[0] = { ...out[0], text } as T;
    else out.shift();
  }
  const last = out[out.length - 1] as unknown as TextToken | undefined;
  if (last?.kind === "text") {
    const text = last.text.trimEnd();
    if (text) out[out.length - 1] = { ...out[out.length - 1], text } as T;
    else out.pop();
  }
  return out;
}

/** Column alignments from the separator row. */
export function alignments<T extends { kind: string }>(separator: T[]): ("left" | "center" | "right")[] {
  return splitCells(separator).map((cell) => {
    const text = cell.map((token) => (token as unknown as TextToken).text).join("").trim();
    if (text.startsWith(":") && text.endsWith(":")) return "center";
    if (text.endsWith(":")) return "right";
    return "left";
  });
}

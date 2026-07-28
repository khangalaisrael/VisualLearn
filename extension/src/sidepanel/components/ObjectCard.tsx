/**
 * One extracted slide object, rendered per-type: equations get real
 * typeset math (MathText/KaTeX) instead of raw LaTeX source, tables get
 * an actual HTML table instead of running the cell text together as one
 * paragraph, everything else gets a plain text/summary layout.
 */

import type { ObjectType, SlideObject } from "@shared/types";

import { MathText } from "./MathText";

const TYPE_STYLES: Record<ObjectType, string> = {
  title: "bg-slate-100 text-slate-700",
  paragraph: "bg-slate-100 text-slate-700",
  equation: "bg-indigo-100 text-indigo-700",
  diagram: "bg-purple-100 text-purple-700",
  graph: "bg-purple-100 text-purple-700",
  table: "bg-amber-100 text-amber-700",
  image: "bg-teal-100 text-teal-700",
};

/**
 * Best-effort parse of extracted_text into rows/columns for `table`-type
 * objects — the VLM isn't asked for a specific table format
 * (prompts/analysis.v3.md), so this recognizes markdown pipe tables and
 * whitespace-aligned tables, and falls back to null (plain text
 * rendering) for anything else rather than guessing wrong.
 */
function parseTable(text: string): string[][] | null {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return null;
  }

  const isSeparatorRow = (line: string) => /^[|\-:\s]+$/.test(line) && line.includes("-");

  const splitLine = (line: string): string[] => {
    if (line.includes("|")) {
      return line
        .split("|")
        .map((cell) => cell.trim())
        .filter((cell, index, cells) => !(cell === "" && (index === 0 || index === cells.length - 1)));
    }
    return line.split(/\s{2,}|\t/).map((cell) => cell.trim());
  };

  const rows = lines.filter((line) => !isSeparatorRow(line)).map(splitLine);
  const columnCount = rows[0]?.length ?? 0;
  if (columnCount < 2 || rows.some((row) => row.length !== columnCount)) {
    return null;
  }
  return rows;
}

function TableView({ rows }: { rows: string[][] }): JSX.Element {
  const [header, ...body] = rows;
  return (
    <div className="overflow-x-auto rounded-sm bg-amber-50/60 shadow-subtle">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {header.map((cell, index) => (
              <th key={index} className="border-b border-amber-200 px-3 py-1.5 text-left font-medium text-amber-900">
                <MathText text={cell} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex} className="odd:bg-white/70">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="border-b border-amber-100 px-3 py-1.5 font-mono tabular-nums text-slate-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ObjectCard({ object }: { object: SlideObject }): JSX.Element {
  const tableRows = object.type === "table" && object.extracted_text ? parseTable(object.extracted_text) : null;

  return (
    <li className="flex flex-col gap-2 rounded-md bg-white p-4 text-sm shadow-subtle">
      <div className="flex items-center justify-between">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${TYPE_STYLES[object.type]}`}
        >
          {object.type}
        </span>
        <span className="font-mono text-xs tabular-nums text-slate-400">
          {Math.round(object.confidence * 100)}% confidence
        </span>
      </div>

      {object.type === "equation" && object.latex && (
        <div className="overflow-x-auto rounded-sm bg-indigo-50/70 px-3 py-2">
          <MathText text={`$$${object.latex}$$`} />
        </div>
      )}

      {object.type === "table" && object.extracted_text ? (
        tableRows ? (
          <TableView rows={tableRows} />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-sm bg-amber-50/70 px-3 py-2 font-mono text-xs text-amber-900">
            {object.extracted_text}
          </pre>
        )
      ) : (
        object.type !== "equation" &&
        object.extracted_text && <p className="text-slate-700">{object.extracted_text}</p>
      )}

      {object.summary && <p className="text-slate-500">{object.summary}</p>}
    </li>
  );
}

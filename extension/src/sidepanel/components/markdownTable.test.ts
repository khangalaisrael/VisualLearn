import { describe, expect, it } from "vitest";

import { alignments, isSeparatorRow, looksLikeRow, splitCells } from "./markdownTable";

type Token = { kind: "text"; text: string } | { kind: "math"; latex: string };
const text = (value: string): Token => ({ kind: "text", text: value });
const math = (latex: string): Token => ({ kind: "math", latex });

describe("isSeparatorRow", () => {
  it("accepts the usual separator rows", () => {
    expect(isSeparatorRow([text("|---|---|")])).toBe(true);
    expect(isSeparatorRow([text("| :--- | :---: | ---: |")])).toBe(true);
    expect(isSeparatorRow([text("---|---")])).toBe(true);
  });

  it("rejects text, a horizontal rule, and rows with formulas", () => {
    expect(isSeparatorRow([text("| a | b |")])).toBe(false);
    expect(isSeparatorRow([text("---")])).toBe(false);
    expect(isSeparatorRow([text("|---|"), math("x")])).toBe(false);
  });
});

describe("splitCells", () => {
  it("drops the outer pipes and trims each cell", () => {
    expect(splitCells([text("| Case | Solution |")])).toEqual([[text("Case")], [text("Solution")]]);
  });

  it("keeps a formula in its cell, even one with bars inside", () => {
    expect(splitCells([text("| 2 | "), math("|x| \\log n"), text(" |")])).toEqual([[text("2")], [math("|x| \\log n")]]);
  });

  it("keeps empty cells in the middle, and escaped pipes as text", () => {
    expect(splitCells([text("| a |  | c \\| d |")])).toEqual([[text("a")], [], [text("c | d")]]);
  });

  it("works without outer pipes", () => {
    expect(splitCells([text("a | b")])).toEqual([[text("a")], [text("b")]]);
  });
});

describe("looksLikeRow and alignments", () => {
  it("sees a pipe only in text", () => {
    expect(looksLikeRow([text("| a | b |")])).toBe(true);
    expect(looksLikeRow([text("absolute value "), math("|x|")])).toBe(false);
  });

  it("reads alignment from colons", () => {
    expect(alignments([text("| :-- | :-: | --: | --- |")])).toEqual(["left", "center", "right", "left"]);
  });
});

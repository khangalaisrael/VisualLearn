import { describe, expect, it } from "vitest";

import { linkLocations, parseDiagnostics } from "./diagnostics";

describe("parseDiagnostics", () => {
  it("reads GHC errors with the message on the next line", () => {
    const output = [
      "prog.hs:3:7: error: [GHC-88464]",
      "    Variable not in scope: lenght :: [a] -> Int",
      "    Suggested fix: Perhaps use 'length'",
    ].join("\n");
    expect(parseDiagnostics(output, 10)).toEqual([
      { line: 3, column: 7, severity: "error", message: "Variable not in scope: lenght :: [a] -> Int" },
    ]);
  });

  it("reads GHC's line ranges and warnings", () => {
    const output = "prog.hs:(2,1)-(3,9): warning: [-Wincomplete-patterns]\n    Pattern match(es) are non-exhaustive";
    expect(parseDiagnostics(output, 5)).toEqual([
      { line: 2, column: 1, severity: "warning", message: "Pattern match(es) are non-exhaustive" },
    ]);
  });

  it("reads javac and g++ errors", () => {
    expect(parseDiagnostics("prog.java:4: error: ';' expected\n    int x = 1\n             ^", 9)).toEqual([
      { line: 4, column: null, severity: "error", message: "';' expected" },
    ]);
    expect(parseDiagnostics("prog.cc:5:3: error: 'cout' was not declared in this scope", 9)).toEqual([
      { line: 5, column: 3, severity: "error", message: "'cout' was not declared in this scope" },
    ]);
  });

  it("puts a Python traceback on the last frame, with the exception as the message", () => {
    const output = [
      "Traceback (most recent call last):",
      '  File "prog.py", line 7, in <module>',
      "    print(twice('a') + 1)",
      '  File "prog.py", line 2, in twice',
      "    return n * 2 + 1",
      "TypeError: can only concatenate str (not \"int\") to str",
    ].join("\n");
    expect(parseDiagnostics(output, 8)).toEqual([
      { line: 2, column: null, severity: "error", message: 'TypeError: can only concatenate str (not "int") to str' },
    ]);
  });

  it("drops lines past the student's code (the runner's own main)", () => {
    expect(parseDiagnostics("prog.hs:14:1: error:\n    Not in scope: 'isPrim'", 6)).toEqual([]);
  });

  it("ignores text that names no place", () => {
    expect(parseDiagnostics("Exception: Prelude.head: empty list", 6)).toEqual([]);
  });
});

describe("linkLocations", () => {
  it("links file:line and 'line N' references inside the code", () => {
    expect(linkLocations('prog.hs:3:7: error\n  File "prog.py", line 2', 5)).toEqual([
      { text: "prog.hs:3:7", line: 3 },
      { text: ': error\n  File "prog.py", ' },
      { text: "line 2", line: 2 },
    ]);
  });

  it("leaves references past the end of the code as text", () => {
    expect(linkLocations("prog.hs:40:1: error", 5)).toEqual([{ text: "prog.hs:40:1: error" }]);
  });
});

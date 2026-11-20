// The backend checks the model's formulas against api/app/katex.json, a list
// of the commands and environments KaTeX supports (decision record 24). It
// must describe the KaTeX this page renders with: after a KaTeX upgrade, run
// `pnpm katex:commands` and commit the new file.

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { katexCommands, OUTPUT, serialize } from "../../scripts/katex-commands";

describe("api/app/katex.json", () => {
  it("lists exactly what the installed KaTeX supports", () => {
    expect(readFileSync(OUTPUT, "utf8")).toBe(serialize(katexCommands()));
  });

  it("knows the commands linear algebra needs", () => {
    const { commands, environments } = katexCommands();
    for (const command of ["frac", "det", "lambda", "begin", "mathbb", "operatorname"]) {
      expect(commands).toContain(command);
    }
    for (const environment of ["pmatrix", "bmatrix", "vmatrix", "cases", "aligned"]) {
      expect(environments).toContain(environment);
    }
    expect(commands).not.toContain("notacommand");
  });
});

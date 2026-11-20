// The LaTeX commands and environments the page's KaTeX can render, written to
// api/app/katex.json so the backend checks the model's formulas against the
// same KaTeX the page renders them with (decision record 24).
//
// Run from web/ after changing KaTeX's version:
//
//   pnpm katex:commands
//
// src/lib/katex-commands.test.ts fails when the file and the installed KaTeX
// disagree.
//
// KaTeX does not export its tables, so the candidates are every command and
// environment name its own source mentions; each one is then rendered, and
// kept unless KaTeX says it does not know it. The file records what KaTeX
// supports, nothing more: which of these a formula may use is the backend's
// decision.

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import katex from "katex";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(WEB, "node_modules", "katex", "src");
export const OUTPUT = join(WEB, "..", "api", "app", "katex.json");

// Commands made of one character other than a letter, such as \, or \{.
const SYMBOLS = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ ";

export type KatexCommands = {
  katex: string;
  commands: string[];
  symbols: string[];
  environments: string[];
};

function files(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? files(join(directory, entry.name))
      : /\.[jt]s$/.test(entry.name)
        ? [join(directory, entry.name)]
        : [],
  );
}

function unknown(tex: string, displayMode: boolean, message: RegExp): boolean {
  try {
    katex.renderToString(tex, {
      displayMode,
      throwOnError: true,
      strict: "ignore",
      trust: false,
    });
    return false;
  } catch (error) {
    return message.test(String(error));
  }
}

export function katexCommands(): KatexCommands {
  // \show and \message write to the console when rendered.
  const log = console.log;
  console.log = () => {};
  try {
    return probe();
  } finally {
    console.log = log;
  }
}

function probe(): KatexCommands {
  const sources = files(SOURCE).map((path) => readFileSync(path, "utf8"));

  const names = new Set<string>();
  for (const text of sources) {
    // In KaTeX's source a command is a string such as "\\frac".
    for (const match of text.matchAll(/["'`]\\\\([A-Za-z]+)/g)) {
      names.add(match[1]);
    }
  }
  const commands = [...names]
    .filter((name) => !unknown(`\\${name}`, false, /Undefined control sequence/))
    .sort();

  const symbols = [...SYMBOLS]
    .filter((c) => !unknown(`\\${c}`, false, /Undefined control sequence/))
    .sort();

  const candidates = new Set<string>();
  for (const text of files(join(SOURCE, "environments")).map((path) =>
    readFileSync(path, "utf8"),
  )) {
    for (const match of text.matchAll(/["']([A-Za-z]+\*?)["']/g)) {
      candidates.add(match[1]);
    }
  }
  const environments = [...candidates]
    .filter(
      (name) =>
        !unknown(`\\begin{${name}}a\\end{${name}}`, true, /No such environment/),
    )
    .sort();

  return { katex: katex.version, commands, symbols, environments };
}

export function serialize(table: KatexCommands): string {
  return `${JSON.stringify(table, null, 1)}\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const table = katexCommands();
  writeFileSync(OUTPUT, serialize(table));
  console.log(
    `KaTeX ${table.katex}: ${table.commands.length} commands, ` +
      `${table.symbols.length} symbols, ${table.environments.length} ` +
      `environments written to ${OUTPUT}`,
  );
}

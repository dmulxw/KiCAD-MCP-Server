#!/usr/bin/env node
/**
 * One-off migration: make an existing .kicad_sch readable by KiCad 9.
 *
 * The schematic in this project was generated before `create_schematic` was
 * fixed to stamp the installed KiCad's format, so it carries a KiCad 10 header
 * (`version 20260101`) -- and, because the symbol loader gates the KiCad 10
 * tokens on that same declared version, two tokens KiCad 9 does not know:
 *
 *     (body_style 1)
 *     (in_pos_files yes)
 *
 * eeschema rejects any of those newer-than-me tokens with a bare "Failed to
 * load schematic", which is what broke `kicad-cli sch export netlist` and, in
 * turn, left `sync_schematic_to_board` adding zero footprints.
 *
 * The result is byte-for-byte what a regenerated schematic would now contain,
 * because the only thing the code fix changes is the header, and these two
 * tokens are emitted purely as a function of it.
 *
 *   node projects/touch-panel/scripts/downgrade-sch-to-kicad9.mjs [path]
 */

import { readFileSync, writeFileSync, renameSync, unlinkSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_SCH = join(HERE, "..", "touch-panel.kicad_sch");

const KICAD9_VERSION = 20250114;
const KICAD9_GENERATOR_VERSION = "9.0";

/** Tokens KiCad 9 rejects, with the reason each one is safe to drop here. */
const KICAD10_LINES = [
  // Presentation-only: which body style a multi-body symbol instance shows.
  // No symbol in this schematic has more than one body style.
  /^\s*\(body_style\s+\d+\)\s*$/,
  // "include in position files" -- an assembly flag. Everything here is placed
  // by the same rule, so the per-symbol override carries no information.
  /^\s*\(in_pos_files\s+\w+\)\s*$/,
];

/**
 * The whole `(version ..) (generator ..) (generator_version ..)` run, however
 * it is wrapped across lines. Rewritten as a unit rather than number-by-number
 * so a rewrite can never leave the three tokens out of step with each other.
 */
const HEADER_RE =
  /\(version\s+\d+\)\s*\(generator\s+"[^"]*"\)\s*\(generator_version\s+"[^"]*"\)/;

/** Paren balance of an s-expression, ignoring parens inside quoted strings. */
function parenBalance(text) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (const ch of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "(") depth += 1;
    else if (ch === ")") depth -= 1;
  }
  return depth;
}

function main() {
  const path = process.argv[2] ?? DEFAULT_SCH;
  const raw = readFileSync(path, "utf8");
  const newline = raw.includes("\r\n") ? "\r\n" : "\n";
  const text = raw.replace(/\r\n/g, "\n");

  const header = text.match(/\((version\s+)(\d+)(\)\s*\(generator\s+"[^"]*"\)\s*\(generator_version\s+")([^"]*)(")/);
  if (!header) {
    throw new Error(`no (version ...) / (generator_version ...) header found in ${path}`);
  }
  if (Number(header[2]) <= KICAD9_VERSION) {
    console.log(`${path} is already at version ${header[2]} -- nothing to do`);
    return;
  }

  const lines = text.split("\n");
  let stripped = 0;
  const kept = lines.filter((line) => {
    if (KICAD10_LINES.some((re) => re.test(line))) {
      stripped += 1;
      return false;
    }
    return true;
  });

  // Refuse to operate on an already-unbalanced file: the strip below is
  // line-based and cannot create or destroy a paren, so an imbalance here means
  // the input was corrupt and rewriting its header would only bury the fault
  // deeper. (An earlier release of this script did exactly that -- it dropped
  // the "(" from the version line, and eeschema reports a missing paren with
  // the same bare "Failed to load schematic" as a too-new version token, which
  // sent the diagnosis chasing KiCad 10 tokens for far too long.)
  const sourceBalance = parenBalance(text);
  if (sourceBalance !== 0) {
    throw new Error(
      `${path} is not balanced (paren depth ${sourceBalance}); refusing to rewrite it`,
    );
  }

  const out = kept.join("\n").replace(
    HEADER_RE,
    // A function replacement is used literally -- no "$1"-style substitution,
    // so the new header cannot be mangled by a digit in the version token
    // being read as a group reference.
    () =>
      `(version ${KICAD9_VERSION}) (generator "eeschema")` +
      ` (generator_version "${KICAD9_GENERATOR_VERSION}")`,
  );

  // The only permitted difference in nesting between in and out is none at all.
  const outBalance = parenBalance(out);
  if (outBalance !== 0) {
    throw new Error(
      `refusing to write ${path}: result is not balanced (paren depth ${outBalance})`,
    );
  }
  if (!HEADER_RE.test(out)) {
    throw new Error(`refusing to write ${path}: header rewrite did not apply`);
  }

  // Atomic, and against the same directory so the rename cannot cross a
  // filesystem: a half-written schematic here would be indistinguishable from
  // a legitimately empty one.
  const tmp = `${path}.mcp-tmp`;
  try {
    writeFileSync(tmp, out.replace(/\n/g, newline), "utf8");
    renameSync(tmp, path);
  } catch (err) {
    try {
      unlinkSync(tmp);
    } catch {
      /* nothing to clean up */
    }
    throw err;
  }

  console.log(`${path}`);
  console.log(`  version   ${header[2]} -> ${KICAD9_VERSION}`);
  console.log(`  generator ${header[4]} -> ${KICAD9_GENERATOR_VERSION}`);
  console.log(`  removed   ${stripped} KiCad 10 token line(s)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

export { main };

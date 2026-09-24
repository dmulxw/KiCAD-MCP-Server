#!/usr/bin/env node
/**
 * Remove every track and via from a board, leaving footprints, nets and zones.
 *
 * `autoroute` exports whatever wiring the board already carries into the DSN,
 * and Freerouting then spends its pass budget optimising that existing copper
 * instead of routing. On this board that is the difference between a run that
 * finishes and one that does not: the first autoroute started from a bare
 * board and completed in ~10 minutes, while re-running it over the 2055
 * segments it had just produced blew through a 600s per-attempt timeout on the
 * very first attempt without finishing.
 *
 * The board this is meant to be run against is a backup-first operation:
 * stripping is cheap and total, so keep a copy of the routed board before
 * calling it.
 *
 *   node projects/touch-panel/scripts/strip-routing.mjs <board> [--dry-run]
 */

import { readFileSync, writeFileSync, renameSync, unlinkSync, existsSync } from "node:fs";
import { pathToFileURL } from "node:url";

/**
 * Drop every top-level `(segment ...)` and `(via ...)` block.
 *
 * Only top-level blocks are considered, and only inside the `(kicad_pcb ...)`
 * body: a `(via` may also appear as a property of something else, and a
 * footprint's own nested markup must survive untouched.
 */
export function stripRouting(text) {
  const OPENERS = ["(segment", "(via"];
  let out = "";
  let i = 0;
  let removed = 0;
  let depth = 0;

  while (i < text.length) {
    const ch = text[i];

    if (ch === '"') {
      const start = i;
      i = skipString(text, i);
      out += text.slice(start, i);
      continue;
    }

    if (ch === "(") {
      if (depth === 1 && OPENERS.some((o) => text.startsWith(o, i))) {
        i = blockEnd(text, i);
        removed += 1;
        continue;
      }
      depth += 1;
      out += ch;
      i += 1;
      continue;
    }

    if (ch === ")") {
      depth -= 1;
      out += ch;
      i += 1;
      continue;
    }

    out += ch;
    i += 1;
  }

  return { text: out, removed };
}

function skipString(text, start) {
  let i = start + 1;
  while (i < text.length) {
    if (text[i] === "\\") i += 2;
    else if (text[i] === '"') return i + 1;
    else i += 1;
  }
  return text.length;
}

function blockEnd(text, start) {
  let depth = 0;
  let i = start;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      i = skipString(text, i);
      continue;
    }
    if (ch === "(") depth += 1;
    else if (ch === ")") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
    i += 1;
  }
  return text.length;
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const board = args.find((a) => !a.startsWith("--"));
  if (!board || !existsSync(board)) {
    throw new Error(`usage: strip-routing.mjs <board.kicad_pcb> [--dry-run]`);
  }

  const raw = readFileSync(board, "utf8");
  const newline = raw.includes("\r\n") ? "\r\n" : "\n";
  const { text, removed } = stripRouting(raw.replace(/\r\n/g, "\n"));

  console.log(`${board}: removed ${removed} segment/via block(s)`);
  if (dryRun) return;

  const tmp = `${board}.mcp-tmp`;
  try {
    writeFileSync(tmp, text.replace(/\n/g, newline), "utf8");
    renameSync(tmp, board);
  } catch (err) {
    try {
      unlinkSync(tmp);
    } catch {
      /* nothing to clean up */
    }
    throw err;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

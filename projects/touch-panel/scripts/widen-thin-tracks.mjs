#!/usr/bin/env node
/**
 * Raise every routed segment below the design minimum back up to it.
 *
 * The board's rule is 0.2mm (see TRACK in layout.mjs), and Freerouting honours
 * it for the overwhelming majority of the routing but necks a handful of
 * segments down to 0.15mm anyway -- 58 of 2055 on the last run. It does so
 * without being forced to: none of those segments is near a via (nearest
 * midpoint-to-via distance was 0.80mm) and only two sit on a column-channel
 * centreline, so they are not squeezing past the fixed geometry this board
 * was laid out around. The DSN it was fed declares the right numbers
 * (`(width 200)` at 1um resolution), so the thinner width is Freerouting's
 * own choice.
 *
 * Measured, not assumed: widening those segments to 0.2mm dropped the track
 * width errors from 58 to 0 and introduced no clearance, mask or silk
 * violation at all. The widened board is strictly better under DRC, which is
 * why this runs as a post-pass rather than trying to talk the router out of it.
 *
 *   node projects/touch-panel/scripts/widen-thin-tracks.mjs [board] [min]
 *
 * Only `(segment ...)` blocks are touched. Pad, text and graphic widths use
 * the same `(width N)` spelling, so a blanket text replacement would corrupt
 * them -- hence the block-aware scan below.
 */

import { readFileSync, writeFileSync, renameSync, unlinkSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_BOARD = join(HERE, "..", "touch-panel.kicad_pcb");
const DEFAULT_MIN = 0.2;

/**
 * Rewrite `(width N)` inside every top-level `(segment ...)` block whose N is
 * below `min`. Returns the new text and how many blocks were raised.
 *
 * The scanner walks paren depth rather than regexing the whole file, because
 * a segment block spans lines and contains nested parens (`(start ...)`,
 * `(net ...)`), which a flat pattern cannot delimit reliably.
 */
export function widenThinSegments(text, min) {
  const isWidth = /^\(width\s/;
  let out = "";
  let i = 0;
  let raised = 0;

  while (i < text.length) {
    const ch = text[i];

    // Skip strings wholesale: a quoted layer/net name could contain a paren.
    if (ch === '"') {
      const start = i;
      i += 1;
      while (i < text.length) {
        if (text[i] === "\\") i += 2;
        else if (text[i] === '"') {
          i += 1;
          break;
        } else i += 1;
      }
      out += text.slice(start, i);
      continue;
    }

    if (ch === "(" && text.startsWith("(segment", i)) {
      const end = blockEnd(text, i);
      const block = text.slice(i, end);
      const next = block.replace(/\(width\s+([0-9.]+)\)/g, (whole, value) => {
        if (parseFloat(value) >= min) return whole;
        raised += 1;
        return `(width ${min})`;
      });
      out += next;
      i = end;
      continue;
    }

    out += ch;
    i += 1;
  }

  return { text: out, raised };
}

/** Index just past the `)` that closes the block opening at `start`. */
function blockEnd(text, start) {
  let depth = 0;
  let i = start;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      i += 1;
      while (i < text.length) {
        if (text[i] === "\\") i += 2;
        else if (text[i] === '"') {
          i += 1;
          break;
        } else i += 1;
      }
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
  const board = process.argv[2] ?? DEFAULT_BOARD;
  const min = Number(process.argv[3] ?? DEFAULT_MIN);

  if (!existsSync(board)) {
    throw new Error(`no board at ${board}`);
  }

  const raw = readFileSync(board, "utf8");
  const newline = raw.includes("\r\n") ? "\r\n" : "\n";
  const { text, raised } = widenThinSegments(raw.replace(/\r\n/g, "\n"), min);

  if (!raised) {
    console.log(`${board}: every segment is already >= ${min}mm`);
    return;
  }

  // Atomic, same directory: a half-written board here would look exactly like
  // a board that lost its routing.
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

  console.log(`${board}`);
  console.log(`  raised ${raised} segment(s) below ${min}mm up to ${min}mm`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

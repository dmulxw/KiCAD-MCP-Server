#!/usr/bin/env node
/**
 * Emit the JSON-RPC request files that turn the finished schematic into a
 * placed PCB. Run each emitted file through scripts/mcp-probe.mjs:
 *
 *   node projects/touch-panel/scripts/generate-pcb-requests.mjs
 *   node scripts/mcp-probe.mjs < projects/touch-panel/scripts/requests/10-setup.jsonl
 *
 * Two facts about the harness shape these files:
 *
 *  1. Every probe run is a fresh `docker run`, so there is NO session state
 *     between files. Each file therefore opens the board, does its work, and
 *     saves -- the board file on disk is the only thing carried across.
 *  2. `sync_schematic_to_board` drops every missing footprint at the board
 *     origin, stacked. `batch_move_components` in the next step is not
 *     optional cleanup, it is what actually places the board.
 *
 * Order matters: sync must run before the moves (the footprints have to exist
 * to be moved), and the moves must run before the vias (a via needs a net, and
 * the nets arrive with the sync).
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  BOARD_W,
  BOARD_H,
  COLS,
  ROWS,
  PAD_COUNT,
  PITCH,
  PAD_DIA,
  TRACK,
  CLEARANCE,
  VIA_DRILL,
  VIA_DIA,
  MOUNT_HOLE_DIA,
  mountingHoles,
  colOf,
  rowOf,
  padIndex,
  PAD,
  COL,
  placements,
  vias,
  padMosfetRef,
  columnSelectRef,
  rowPulldownRef,
  cselPulldownRef,
  touchPadRef,
  mosfetPos,
  columnSelectPos,
  rowPulldownPos,
  cselPulldownPos,
  touchPadPos,
  J1_POS,
} from "./layout.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "requests");

// --- container-side paths -------------------------------------------------
const PROJECT = "/workspace/projects/touch-panel";
const SCH = `${PROJECT}/touch-panel.kicad_sch`;
const PCB = `${PROJECT}/touch-panel.kicad_pcb`;

const lines = [];
const emit = (obj) => lines.push(JSON.stringify(obj));
const call = (name, args) => emit({ method: "tools/call", params: { name, arguments: args } });

function header() {
  return [
    JSON.stringify({
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "touch-panel-pcb", version: "1.0" },
      },
    }),
    JSON.stringify({ method: "notifications/initialized" }),
  ];
}

function write(name, body) {
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(join(OUT_DIR, name), [...header(), ...body].join("\n") + "\n", "utf8");
  console.log(`wrote ${name}  (${body.length} calls)`);
}

const flush = () => lines.splice(0, lines.length);

// =========================================================================
// 10 -- design rules
// =========================================================================
// The 6.4mm pad pitch leaves 1.4mm between pads, so 0.2/0.2 is not a
// preference here, it is the number the whole layout was derived against:
// one column track needs 0.2 + 0.2 + 0.2 = 0.6mm of the 1.4mm channel, and a
// 0.6mm via needs the full 1.2mm.
call("open_board", { boardPath: PCB });
call("set_design_rules", {
  clearance: CLEARANCE,
  trackWidth: TRACK,
  viaDiameter: VIA_DIA,
  viaDrill: VIA_DRILL,
  minTrackWidth: TRACK,
  minViaDiameter: VIA_DIA,
  minViaDrill: VIA_DRILL,
  minHoleDiameter: VIA_DRILL,
});
// A courtyard requirement would flag the 210 touch pads: TouchPadColumn was
// written without one on purpose, because a front-side courtyard would collide
// with the MOSFET sitting directly above each pad.
call("set_design_rules", { requireCourtyard: false });

call("save_project", {});
call("get_design_rules", {});
write("10-setup.jsonl", flush());

// =========================================================================
// 11 -- pull the schematic onto the board
// =========================================================================
// This is the F8-equivalent. It creates every missing footprint -- all 262 of
// them -- assigns nets pad by pad, and saves. Every footprint lands at (0, 0),
// which is why 12-place exists.
call("open_board", { boardPath: PCB });
call("sync_schematic_to_board", { schematicPath: SCH, boardPath: PCB });
call("save_project", {});
call("get_board_info", { boardPath: PCB });
write("11-sync.jsonl", flush());

// =========================================================================
// 12 -- place all 262 footprints
// =========================================================================
// Chunked so a single bad reference cannot cost the whole placement, and so
// progress is visible in the probe output.
const moves = {};

for (let c = 0; c < COLS; c++) {
  const p = touchPadPos(c);
  moves[touchPadRef(c)] = { x: p.x, y: p.y, rotation: 0 };
}
for (let n = 1; n <= PAD_COUNT; n++) {
  const p = mosfetPos(n);
  // Rotation 0 puts the gate (pin 1) above the row line and the source (pin 2)
  // below it, so the gate stub is a straight drop and the source stub runs
  // left without ever crossing it.
  moves[padMosfetRef(n)] = { x: p.x, y: p.y, rotation: 0 };
}
for (let c = 0; c < COLS; c++) {
  const p = columnSelectPos(c);
  moves[columnSelectRef(c)] = { x: p.x, y: p.y, rotation: 0 };
}
for (let r = 0; r < ROWS; r++) {
  const p = rowPulldownPos(r);
  moves[rowPulldownRef(r)] = { x: p.x, y: p.y, rotation: 0 };
}
for (let c = 0; c < COLS; c++) {
  const p = cselPulldownPos(c);
  moves[cselPulldownRef(c)] = { x: p.x, y: p.y, rotation: 0 };
}
moves["J1"] = { x: J1_POS.x, y: J1_POS.y, rotation: 0 };

const CHUNK = 70;
const refs = Object.keys(moves);
const chunks = [];
for (let i = 0; i < refs.length; i += CHUNK) {
  const slice = {};
  for (const ref of refs.slice(i, i + CHUNK)) slice[ref] = moves[ref];
  chunks.push(slice);
}

call("open_board", { boardPath: PCB });
for (const slice of chunks) {
  call("batch_move_components", { moves: slice, save: true, unit: "mm" });
}
call("save_project", {});
call("check_courtyard_overlaps", {});
call("get_board_info", { boardPath: PCB });
write("12-place.jsonl", flush());
console.log(`  (planned ${refs.length} footprints in ${chunks.length} batches)`);

// =========================================================================
// 12b -- repair: duplicate mounting holes
// =========================================================================
// The board frame was built in two passes during setup, so its four holes
// exist twice over: MH1-MH4 where `mountingHoles()` puts them and MH5-MH8
// stacked exactly on top. Two footprints at one coordinate read as a hard
// courtyard overlap (MH1 vs MH5) and would drill each hole twice, which a
// 2.7mm hole in a 5.5mm-deep margin will not survive. The lower-numbered ref
// at each position is the one the frame step owns, so the second set goes.
//
// On a clean build these refs do not exist and each call answers "Component
// not found", which is why a failed delete is tolerated here rather than
// treated as an error.
const holes = mountingHoles();
call("open_board", { boardPath: PCB });
for (let i = 1; i <= holes.length; i += 1) {
  call("delete_component", { reference: `MH${holes.length + i}` });
}
call("save_project", {});
call("check_courtyard_overlaps", {});
write("12b-fix-mount-holes.jsonl", flush());
console.log(`  (removes up to ${holes.length} duplicate mounting holes)`);

// =========================================================================
// 13 / 14 -- the 420 pad vias
// =========================================================================
// `add_via` is one via per call; there is no bulk form that takes arbitrary
// coordinates. Split drain and source so the drain file can be re-run without
// duplicating the sources if something fails halfway.
const drain = vias().filter((v) => v.role === "drain");
const source = vias().filter((v) => v.role === "source");

for (const [name, group, note] of [
  ["13-vias-drain.jsonl", drain, "drain"],
  ["14-vias-source.jsonl", source, "source"],
]) {
  call("open_board", { boardPath: PCB });
  for (const v of group) {
    // unit is optional in the schema but the handler reads it unguarded, so
    // omitting it raises rather than defaulting.
    call("add_via", { position: { x: v.x, y: v.y, unit: "mm" }, net: v.net, viaType: "through" });
  }
  call("save_project", {});
  call("get_board_info", { boardPath: PCB });
  write(name, flush());
  console.log(`  (${group.length} ${note} vias)`);
}

// =========================================================================
// 15 -- verification
// =========================================================================
// Targeted reads rather than a full board dump: enough to prove the pads sit
// on B.Cu under their own MOSFETs, that the pile-up at the origin is empty,
// and that the nets came across.
call("open_board", { boardPath: PCB });
call("get_board_info", { boardPath: PCB });

// TP1 is pad column 0: 21 pads at 6.4mm pitch, expected on B.Cu with nets
// PAD1, PAD11, PAD21 ... PAD201.
call("get_pads", { reference: "TP1" });
// Q1 is the MOSFET for PAD1; its pin 3 must carry net PAD1.
call("get_pads", { reference: "Q1" });
// Q210 is the last pad MOSFET, PAD210 (row 20, column 9).
call("get_pads", { reference: "Q210" });
// A midpoint, to catch a row/column transposition that the corners would miss.
call("get_pads", { reference: `Q${padIndex(10, 5)}` });
call("get_component_geometry", { reference: "Q1" });
call("get_component_geometry", { reference: "TP1" });
call("check_courtyard_overlaps", {});
call("check_placement_clearance", {});
call("get_nets_list", {});
write("15-verify.jsonl", flush());

// =========================================================================
// 16 -- autoroute + DRC
// =========================================================================
// Best-of-N: this board is unusually dense for Freerouting -- 253 nets, 420
// fixed vias and a 0.2/0.2 rule inside 1.4mm channels -- and it left 7 nets
// stranded on the first run.
//
// `attempts: 6` matches the length of the default strategySchedule so the run
// covers all six (-is, -us) combinations exactly once. Cycling `-mp` alone
// bought nothing: the router is deterministic once it converges, and five
// attempts returned five identical boards down to the same 7 unrouted nets.
// `-is` (which items each optimiser round examines) is what moves the search.
//
// Run `strip-routing.mjs` on the board BEFORE this file. `autoroute` exports
// whatever wiring the board already carries into the DSN, and Freerouting then
// spends its passes optimising that copper instead of routing: re-running over
// the 2055 segments of a previous result did not finish a single attempt
// inside 600s, where the same router on a bare board completes the whole
// best-of-N in about that long.
//
// There is deliberately no `save_project` after the autoroute: importing the
// SES persists the board itself, so a save here is refused with
// `diskChangedExternally` and only obscures whether the import actually
// happened. `keepArtifacts` leaves the DSN/SES beside the board, since when
// DRC disagrees with the router the SES is the only record of what the router
// believed it had done.
call("open_board", { boardPath: PCB });
call("autoroute", {
  boardPath: PCB,
  attempts: 6,
  timeout: 900,
  keepArtifacts: true,
});
call("run_drc", {});
call("get_drc_violations", {});
write("16-route.jsonl", flush());

// --- summary ---------------------------------------------------------------
console.log(`\nboard ${BOARD_W}x${BOARD_H}mm, ${PAD_COUNT} pads at ${PITCH}mm pitch (D${PAD_DIA})`);
console.log(`component footprints: ${refs.length}`);
console.log(`vias: ${vias().length} (${drain.length} drain + ${source.length} source)`);
console.log(`rules: track ${TRACK}mm, clearance ${CLEARANCE}mm, via ${VIA_DIA}/${VIA_DRILL}mm, mount hole D${MOUNT_HOLE_DIA}`);
console.log(`pad grid: ${COLS} cols x ${ROWS} rows; J1 at (${J1_POS.x}, ${J1_POS.y})`);

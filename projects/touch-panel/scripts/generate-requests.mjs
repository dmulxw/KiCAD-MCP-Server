#!/usr/bin/env node
/**
 * Emit the JSON-RPC request files that build the touch-panel board through the
 * KiCAD MCP server. Run each emitted file through scripts/mcp-probe.mjs:
 *
 *   node projects/touch-panel/scripts/generate-requests.mjs
 *   node scripts/mcp-probe.mjs < projects/touch-panel/scripts/requests/01-*.jsonl
 *
 * Design being generated
 * ----------------------
 * 210 capacitive touch pads on a 71x150mm board, addressed as a 21-row by
 * 10-column matrix. Each pad gets its own N-MOSFET; grounding a pad through
 * that MOSFET is what the phone's touch controller reads as a finger.
 *
 *   Q1..Q210   pad MOSFETs.  G = ROW<r>, S = COL<c>, D = the pad itself
 *   Q211..Q220 column select. G = CSEL<c>, D = COL<c>, S = GND
 *   R1..R31    10k gate pull-downs, one per ROW and per CSEL line
 *   J1         40-pin 0.5mm FPC to the control board (carries the 31 selects)
 *   TP1..TP10  the touch pads, folded into the netlist as ten 21-pin columns
 *
 * Grounding only happens where a ROW line and its CSEL line are both driven,
 * so exactly one pad is ever active -- no multi-touch, by design.
 *
 * Geometry: 10 columns at 6.4mm pitch span 62.6mm of the 71mm width; 21 rows at
 * 6.4mm pitch span 133mm of the 150mm height. That leaves a 1.4mm channel
 * between adjacent 5mm pads for the via that ties each pad to its MOSFET.
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "requests");

// --- container-side paths -------------------------------------------------
const PROJECT = "/workspace/projects/touch-panel";
const SCH = `${PROJECT}/touch-panel.kicad_sch`;
const FPLIB = `${PROJECT}/libs/touch-panel.pretty`;
const SYMLIB = `${PROJECT}/libs/touch-panel.kicad_sym`;

// --- board geometry -------------------------------------------------------
const BOARD_W = 71;
const BOARD_H = 150;
const COLS = 10;
const ROWS = 21;
const PITCH = 6.4;
const PAD_DIA = 5.0;
const MOUNT_HOLE_DIA = 2.7; // M2.5 clearance
const PAD_COUNT = COLS * ROWS; // 210

// The board is placed at (100, 100) rather than the sheet origin: Gerber and
// drill writers are happier with coordinates that stay positive, and it keeps
// the outline clear of the origin so a stray 0,0 is obviously wrong.
const ORIGIN_X = 100;
const ORIGIN_Y = 100;

const CX = BOARD_W / 2;
const CY = BOARD_H / 2;
/** Absolute board coords: relative position plus the placement origin. */
const colX = (c) => ORIGIN_X + CX + (c - (COLS - 1) / 2) * PITCH;
const rowY = (r) => ORIGIN_Y + CY + (r - (ROWS - 1) / 2) * PITCH;

/** 1-based pad index for the pad at row r, column c. */
const padIndex = (r, c) => r * COLS + c + 1;
const rowOf = (n) => Math.floor((n - 1) / COLS);
const colOf = (n) => (n - 1) % COLS;

// --- net names ------------------------------------------------------------
const PAD = (n) => `PAD${n}`;
const ROW = (r) => `ROW${r}`;
const COL = (c) => `COL${c}`;
const CSEL = (c) => `CSEL${c}`;
const GND = "GND";
const V33 = "+3V3";

// --- schematic placement grids -------------------------------------------
// Deliberately roomy: the sheet is A2 and the point of the layout is that no
// two symbols or labels land on top of each other, not that it reads prettily.
const mosPos = (n) => ({ x: 30 + colOf(n) * 18, y: 30 + rowOf(n) * 14 });
const colSelPos = (c) => ({ x: 30 + c * 18, y: 340 });
const tpPos = (c) => ({ x: 230 + c * 16, y: 30 });
const pulldownPos = (i) => ({ x: 410, y: 40 + i * 10 });

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
        clientInfo: { name: "touch-panel-builder", version: "1.0" },
      },
    }),
    JSON.stringify({ method: "notifications/initialized" }),
  ];
}

function write(name, body) {
  mkdirSync(OUT_DIR, { recursive: true });
  const path = join(OUT_DIR, name);
  writeFileSync(path, [...header(), ...body].join("\n") + "\n", "utf8");
  console.log(`wrote ${name}  (${body.length} calls)`);
}

function flush() {
  const body = lines.splice(0, lines.length);
  return body;
}

// =========================================================================
// 01 -- custom library: one 21-pad footprint and its matching 21-pin symbol
// =========================================================================

// Pads live on B.Cu only: the board is laid copper-side-down on the screen, and
// B.Mask keeps them exposed for ENIG. No B.Paste -- nothing is soldered here.
// No courtyard either; a courtyard on the front would collide with the 210
// MOSFETs sitting directly above these pads.
const pads = [];
for (let r = 0; r < ROWS; r++) {
  pads.push({
    number: String(r + 1),
    type: "smd",
    shape: "circle",
    at: { x: 0, y: (r - (ROWS - 1) / 2) * PITCH },
    size: { w: PAD_DIA, h: PAD_DIA },
    layers: ["B.Cu", "B.Mask"],
  });
}

call("create_footprint", {
  libraryPath: FPLIB,
  name: "TouchPadColumn",
  description:
    `Column of ${ROWS} capacitive touch pads, ${PAD_DIA}mm, ${PITCH}mm pitch, exposed on B.Cu`,
  tags: "touch pad capacitive custom",
  pads,
  overwrite: true,
});
call("register_footprint_library", {
  libraryPath: FPLIB,
  libraryName: "touch-panel",
  description: "Touch panel project footprints",
  scope: "project",
  projectPath: `${PROJECT}/touch-panel.kicad_pro`,
});

// 21 pins down the left edge at 2.54mm pitch, so the symbol is 53mm tall.
// 1.27mm would halve that but crowd the net labels placed on each pin.
const pins = [];
for (let r = 0; r < ROWS; r++) {
  pins.push({
    name: "~",
    number: String(r + 1),
    type: "passive",
    at: { x: -7.62, y: ((ROWS - 1) / 2 - r) * 2.54, angle: 0 },
    length: 2.54,
  });
}
call("create_symbol", {
  libraryPath: SYMLIB,
  name: "TouchPadColumn",
  referencePrefix: "TP",
  description: `Column of ${ROWS} capacitive touch pads`,
  keywords: "touch pad capacitive",
  datasheet: "~",
  footprint: "touch-panel:TouchPadColumn",
  inBom: false, // bare copper, not a purchased part
  onBoard: true, // but it must still reach the netlist
  pins,
  rectangles: [
    {
      x1: -5.08,
      y1: -((ROWS - 1) / 2) * 2.54 - 2.54,
      x2: 5.08,
      y2: ((ROWS - 1) / 2) * 2.54 + 2.54,
      fill: "background",
    },
  ],
  overwrite: true,
});
call("register_symbol_library", {
  libraryPath: SYMLIB,
  libraryName: "touch-panel",
  description: "Touch panel project symbols",
  scope: "project",
  projectPath: `${PROJECT}/touch-panel.kicad_pro`,
});
write("01-libs.jsonl", flush());

// =========================================================================
// 02 -- the 210 pad MOSFETs
// =========================================================================
// Chunked because a single 210-component call makes for a very large request
// and a single point of failure.
const CHUNK = 42;
for (let start = 1; start <= PAD_COUNT; start += CHUNK) {
  const components = [];
  for (let n = start; n < Math.min(start + CHUNK, PAD_COUNT + 1); n++) {
    const r = rowOf(n);
    const c = colOf(n);
    components.push({
      symbol: "Transistor_FET:Q_NMOS_GSD",
      reference: `Q${n}`,
      value: "AO3400",
      footprint: "Package_TO_SOT_SMD:SOT-23",
      position: mosPos(n),
      nets: { 1: ROW(r), 2: COL(c), 3: PAD(n) },
    });
  }
  call("batch_add_and_connect", { schematicPath: SCH, components });
  const tag = String(start).padStart(3, "0");
  write(`02-mosfets-${tag}.jsonl`, flush());
}

// =========================================================================
// 03 -- column selects, pull-downs, connector, touch pads
// =========================================================================
const support = [];

// Column-select FETs. Draining COL<c> to GND only when CSEL<c> is driven is
// half the matrix address; the row gate is the other half.
for (let c = 0; c < COLS; c++) {
  support.push({
    symbol: "Transistor_FET:Q_NMOS_GSD",
    reference: `Q${PAD_COUNT + c + 1}`,
    value: "AO3400",
    footprint: "Package_TO_SOT_SMD:SOT-23",
    position: colSelPos(c),
    nets: { 1: CSEL(c), 2: GND, 3: COL(c) },
  });
}

// One pull-down per select line, not per MOSFET. The shift register on the
// control board is Hi-Z until it is first written, and a floating gate line
// would let all 210 pads float high together.
let rIdx = 0;
for (let r = 0; r < ROWS; r++) {
  support.push({
    symbol: "Device:R",
    reference: `R${++rIdx}`,
    value: "10k",
    footprint: "Resistor_SMD:R_0402_1005Metric",
    position: pulldownPos(rIdx - 1),
    nets: { 1: ROW(r), 2: GND },
  });
}
for (let c = 0; c < COLS; c++) {
  support.push({
    symbol: "Device:R",
    reference: `R${++rIdx}`,
    value: "10k",
    footprint: "Resistor_SMD:R_0402_1005Metric",
    position: pulldownPos(rIdx - 1),
    nets: { 1: CSEL(c), 2: GND },
  });
}

// J1 pinout: 1-21 rows, 22-31 column selects, 32-36 ground, 37-40 3V3.
// 31 signals + power + ground is what the 40-way FPC is sized for.
const j1Nets = {};
for (let r = 0; r < ROWS; r++) j1Nets[r + 1] = ROW(r);
for (let c = 0; c < COLS; c++) j1Nets[ROWS + 1 + c] = CSEL(c);
for (let p = 32; p <= 36; p++) j1Nets[p] = GND;
for (let p = 37; p <= 40; p++) j1Nets[p] = V33;
support.push({
  symbol: "Connector:Conn_01x40_Pin",
  reference: "J1",
  value: "FPC-40P-0.5mm",
  footprint: "Connector_FFC-FPC:Hirose_FH12-40S-0.5SH_1x40-1MP_P0.50mm_Horizontal",
  position: { x: 470, y: 60 },
  nets: j1Nets,
});

// The pads themselves. Pin (r+1) of TP<c+1> is pad (r, c) of the matrix.
for (let c = 0; c < COLS; c++) {
  const nets = {};
  for (let r = 0; r < ROWS; r++) nets[r + 1] = PAD(padIndex(r, c));
  support.push({
    symbol: "touch-panel:TouchPadColumn",
    reference: `TP${c + 1}`,
    value: "TouchPadColumn",
    footprint: "touch-panel:TouchPadColumn",
    position: tpPos(c),
    nets,
  });
}
call("batch_add_and_connect", { schematicPath: SCH, components: support });
write("03-support.jsonl", flush());

// =========================================================================
// 03b -- power flags
// =========================================================================
// The 40-way FPC is the only thing feeding this board, so nothing on the sheet
// drives GND or +3V3 and ERC reports both as undriven power pins. PWR_FLAG is
// KiCad's way of saying "this net is driven from off-sheet".
call("batch_add_and_connect", {
  schematicPath: SCH,
  components: [
    { symbol: "power:PWR_FLAG", reference: "#FLG01", value: "PWR_FLAG", position: { x: 520, y: 100 }, nets: { 1: GND } },
    { symbol: "power:PWR_FLAG", reference: "#FLG02", value: "PWR_FLAG", position: { x: 520, y: 115 }, nets: { 1: V33 } },
  ],
});
write("03b-pwrflag.jsonl", flush());

// =========================================================================
// 04 -- board outline, mounting holes, DXF
// =========================================================================
// The board tools act on the session's loaded board, not on a path argument,
// so the file has to be opened first in this same process.
call("open_board", { boardPath: `${PROJECT}/touch-panel.kicad_pcb` });
call("replace_board_outline", {
  shape: "rectangle",
  params: { x: ORIGIN_X, y: ORIGIN_Y, width: BOARD_W, height: BOARD_H, unit: "mm" },
});

// Holes sit in the top and bottom margins, inboard of the corner, rather than
// in the corners proper: the outer pad columns reach to within 4.2mm of the
// side edges, so a 2.7mm hole in a corner would foul them. There is 11mm of
// clear margin above row 0 and below row 20 -- 1.65mm of air between the hole
// edge and the nearest pad edge.
const holeInsetX = 8;
const holeInsetY = 5.5;
for (const hx of [holeInsetX, BOARD_W - holeInsetX]) {
  for (const hy of [holeInsetY, BOARD_H - holeInsetY]) {
    call("add_mounting_hole", {
      position: { x: ORIGIN_X + hx, y: ORIGIN_Y + hy, unit: "mm" },
      diameter: MOUNT_HOLE_DIA,
    });
  }
}

// export_pcb_dxf plots the last SAVED state, so the edits above have to reach
// disk before it runs.
call("save_project", {});
// The plotter defaults to one file per layer into a directory, and to inches.
// Both are wrong for a mechanical drawing that gets imported back into a CAD
// tool alongside mm dimensions.
call("export_pcb_dxf", {
  boardPath: `${PROJECT}/touch-panel.kicad_pcb`,
  outputPath: `${PROJECT}/touch-panel-outline.dxf`,
  layers: ["Edge.Cuts"],
  modeSingle: true,
  outputUnits: "mm",
  excludeRefdes: true,
  excludeValue: true,
  includeBorderTitle: false,
});
call("get_board_info", { boardPath: `${PROJECT}/touch-panel.kicad_pcb` });
write("04-board.jsonl", flush());

// =========================================================================
// 05 -- verification
// =========================================================================
// `list_schematic_nets` walks every symbol and is far too slow to be worth
// running against a 262-component sheet, and GND alone has 250+ connections.
// These targeted lookups pin down the same facts in a fraction of the time.
//
// The matrix claim to prove is that pad(i,j) hangs off exactly one drain, that
// each ROW reaches its ten gates, and that each COL reaches its twenty-one
// sources plus its column-select drain. Corners catch an off-by-one in either
// index; the middle catches a row/column transposition that the corners would
// not.
const padsToCheck = [1, 2, 10, 11, 105, 106, 200, 209, 210];
for (const n of padsToCheck) {
  call("get_net_connections", { schematicPath: SCH, netName: PAD(n) });
}
for (const r of [0, 1, 9, 10, 19, 20]) {
  call("get_net_connections", { schematicPath: SCH, netName: ROW(r) });
}
for (const c of [0, 1, 4, 5, 8, 9]) {
  call("get_net_connections", { schematicPath: SCH, netName: COL(c) });
}
for (const c of [0, 9]) {
  call("get_net_connections", { schematicPath: SCH, netName: CSEL(c) });
}
// The case where column and row indices disagree, which is what exposes a
// swapped index in either direction.
call("get_net_connections", { schematicPath: SCH, netName: PAD(padIndex(3, 7)) });
call("get_net_connections", { schematicPath: SCH, netName: ROW(3) });
write("05-verify.jsonl", flush());

console.log(`\nboard: ${BOARD_W}x${BOARD_H}mm, ${PAD_COUNT} pads at ${PITCH}mm pitch`);
console.log(`pad columns span ${(COLS - 1) * PITCH + PAD_DIA}mm, rows span ${(ROWS - 1) * PITCH + PAD_DIA}mm`);

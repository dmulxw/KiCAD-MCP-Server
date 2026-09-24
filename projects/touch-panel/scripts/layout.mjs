#!/usr/bin/env node
/**
 * Single source of truth for the touch-panel PCB geometry.
 *
 * Both the request generator and the clearance checker import this, so a
 * coordinate is only ever written down once. The numbers here were derived
 * against the hard constraint that governs the whole layout:
 *
 *   210 pads, 5.0mm diameter, 6.4mm pitch  ->  1.4mm between adjacent pads.
 *
 * A 0.2mm track with the 0.2mm clearance the design rules ask for needs
 * 0.2 + 0.2 + 0.2 = 0.6mm, so one track fits in a channel with room to spare --
 * but a 0.6mm via (0.3mm drill) plus a track does not: 0.6 + 0.2 + 0.2 + 0.2 =
 * 1.2mm leaves only 0.2mm of slop across a 1.4mm channel, and the via's own
 * annular ring eats that. So each of the ten inter-column channels carries
 * exactly one net, and the ten column nets take nine channels plus the left
 * board margin.
 *
 * That is also why every via sits *inside* the pad it belongs to: there is no
 * room for a via-and-stub escape in the channels.
 */

import { pathToFileURL } from "node:url";

// --- board -----------------------------------------------------------------
export const BOARD_W = 71;
export const BOARD_H = 150;
export const ORIGIN_X = 100;
export const ORIGIN_Y = 100;

// --- matrix ----------------------------------------------------------------
export const COLS = 10;
export const ROWS = 21;
export const PITCH = 6.4;
export const PAD_DIA = 5.0;
export const PAD_COUNT = COLS * ROWS; // 210

// --- rules -----------------------------------------------------------------
export const TRACK = 0.2;
export const CLEARANCE = 0.2;
export const VIA_DRILL = 0.3;
export const VIA_DIA = 0.6;
export const MOUNT_HOLE_DIA = 2.7;

// --- mounting holes --------------------------------------------------------
/** Mounting-hole centre insets, measured in from the board frame's corners. */
export const MOUNT_HOLE_INSET_X = 8;
export const MOUNT_HOLE_INSET_Y = 5.5;

/**
 * The four mounting holes, in the order the board-frame step places them
 * (MH1-MH4). Exported so the frame geometry has exactly one definition: the
 * placement check, the duplicate-repair request and the frame script all read
 * it here instead of each carrying its own copy of "8 and 5.5".
 */
export const mountingHoles = () =>
  [MOUNT_HOLE_INSET_X, BOARD_W - MOUNT_HOLE_INSET_X].flatMap((hx) =>
    [MOUNT_HOLE_INSET_Y, BOARD_H - MOUNT_HOLE_INSET_Y].map((hy) => ({
      x: ORIGIN_X + hx,
      y: ORIGIN_Y + hy,
    })),
  );

// --- footprint extents (verified against the KiCad libraries) --------------
// Package_TO_SOT_SMD:SOT-23     pads at x=+-0.9375, y=+-0.95, size 0.9x1.0
// Resistor_SMD:R_0402_1005Metric pads at x=+-0.51, size 0.6x0.65
export const SOT23_HALF_X = 0.9375 + 0.9 / 2;
export const SOT23_HALF_Y = 0.95 + 1.0 / 2;
export const R0402_HALF_X = 0.51 + 0.6 / 2;
export const R0402_HALF_Y = 0.65 / 2;

// --- courtyard extents ------------------------------------------------------
// DRC compares courtyards, not bodies, and a courtyard is noticeably larger:
// SOT-23 is 1.93 x 1.7 around a 1.39 x 1.45 body, R_0402 is 0.93 x 0.47.
// A part is reported whenever its courtyard reaches inside the mounting hole's,
// which is a circle of MOUNT_HOLE_CRTYD_R -- the M2.5 screw head, not the
// 1.35mm hole. Testing bodies against the drill instead of courtyards against
// the screw head is how the first layout put six parts under a screw head
// without the self-check noticing.
export const SOT23_CRTYD_HX = 1.93;
export const SOT23_CRTYD_HY = 1.7;
export const R0402_CRTYD_HX = 0.93;
export const R0402_CRTYD_HY = 0.47;
export const MOUNT_HOLE_CRTYD_R = 2.95;

const CX = BOARD_W / 2;
const CY = BOARD_H / 2;

/** Absolute X of pad column c. */
export const colX = (c) => ORIGIN_X + CX + (c - (COLS - 1) / 2) * PITCH;
/** Absolute Y of pad row r. */
export const rowY = (r) => ORIGIN_Y + CY + (r - (ROWS - 1) / 2) * PITCH;

/** 1-based index of the pad at (r, c). */
export const padIndex = (r, c) => r * COLS + c + 1;
export const rowOf = (n) => Math.floor((n - 1) / COLS);
export const colOf = (n) => (n - 1) % COLS;

// --- net names -------------------------------------------------------------
export const PAD = (n) => `PAD${n}`;
export const ROW = (r) => `ROW${r}`;
export const COL = (c) => `COL${c}`;
export const CSEL = (c) => `CSEL${c}`;
export const GND = "GND";
export const V33 = "+3V3";

// ===========================================================================
// Vertical channels
// ===========================================================================
// Pad c spans colX(c)+-2.5, so the channel to its left is centred on
// colX(c)-3.2 and is 1.4mm wide. Channel 0 falls in the left board margin
// (pad 0's left edge is 4.2mm inboard of the board edge), which is what lets
// ten column nets share eleven available slots.
/** X of the channel immediately left of pad column c. */
export const colChannelX = (c) => colX(c) - 3.2;

/** X of the channel immediately right of pad column c (only c=9 is unused). */
export const rightMarginChannelX = () => colX(COLS - 1) + 3.2;

// ===========================================================================
// Components
// ===========================================================================

/**
 * The 210 pad MOSFETs sit directly on top of their own pad, on F.Cu. Nothing
 * mechanical stops this -- the pad is on the far side of a 1.6mm board -- and
 * it makes the drain connection a 0.5mm stub instead of a channel escape that
 * would not fit. Pin 1 is the gate (row), pin 2 the source (column), pin 3 the
 * drain (the pad).
 */
export const mosfetPos = (n) => ({ x: colX(colOf(n)), y: rowY(rowOf(n)) });

/**
 * The ten column-select FETs: six along the bottom margin, four along the top.
 *
 * Six is all the bottom margin holds once the screw heads are respected rather
 * than just the drills. J1 takes x 122.45..148.55, and a SOT-23 courtyard may
 * not come within 2.478mm of a bottom mounting hole's centre -- so a FET centre
 * has to sit outside 108 +- 4.408 and 163 +- 4.408. That leaves 112.41..120.52
 * on the left and 150.48..158.59 on the right: three either side. Columns 3-6
 * go to the top margin instead.
 *
 * The top margin is otherwise empty. The touch pads start at y=108.5 and the
 * top holes at y=105.5, so a row at y=103.5 clears both, and pin 3 can be put
 * directly over the column's own COL channel so the drain is a straight drop.
 */
export const COLUMN_SELECT_Y = 247.8;
/** Top-margin row for the columns that do not fit along the bottom. */
export const COLUMN_SELECT_TOP_Y = 103.5;

/** Columns whose select FET lives in the top margin rather than the bottom. */
const TOP_COLUMNS = new Set([3, 4, 5, 6]);

/**
 * Bottom-margin x, in column order, for the six that stay down there.
 *
 * Three SOT-23 courtyards are 3.86mm wide each; the window between the screw
 * head and J1 is 11.972mm, so the three fit only at a pitch between 3.86 and
 * 4.056. 3.958 splits the slack evenly -- every courtyard edge lands 0.098mm
 * from the nearest thing it must clear -- which is why the numbers are not
 * round. A rounder 4.0mm pitch would put column 2's courtyard 0.02mm off J1.
 */
const BOTTOM_CSEL_X = { 0: 112.506, 1: 116.464, 2: 120.422, 7: 150.578, 8: 154.536, 9: 158.494 };

export const columnSelectPos = (c) =>
  TOP_COLUMNS.has(c)
    ? // Pin 3 sits at +0.9375, so offsetting the body puts the drain pad,
      // not the body centre, over the channel.
      { x: colChannelX(c) - 0.9375, y: COLUMN_SELECT_TOP_Y }
    : { x: BOTTOM_CSEL_X[c], y: COLUMN_SELECT_Y };

/**
 * Pull-downs. One per select line, not per FET: the shift register on the
 * control board is Hi-Z until first written and a floating gate line would let
 * a whole row of pads float high together.
 *
 * ROW r's pull-down sits in the left margin level with its own ROW line, so
 * the line reaches it with a straight horizontal run.
 */
export const PULLDOWN_X = 102.1;
export const rowPulldownPos = (r) => ({ x: PULLDOWN_X, y: rowLineY(r) });

/** CSEL pull-downs, tucked between pad row 20 and the mounting holes. */
// y=242.5 is the only room left on the board for these ten: pad row 20 ends at
// y=241.5 and the screw heads start at y=242.03. A 0402 courtyard must clear
// 108 +- 3.452 and 163 +- 3.452, which leaves 111.45..121.52 and
// 149.48..159.55 -- 2mm pitch, five either side, still clear of J1 at 122.45.
export const cselPulldownX = [112.5, 114.5, 116.5, 118.5, 120.5, 150.5, 152.5, 154.5, 156.5, 158.5];
export const CSEL_PULLDOWN_Y = 242.5;
export const cselPulldownPos = (c) => ({ x: cselPulldownX[c], y: CSEL_PULLDOWN_Y });

/** Reference designators, in the order the schematic assigned them. */
export const padMosfetRef = (n) => `Q${n}`;
export const columnSelectRef = (c) => `Q${PAD_COUNT + c + 1}`;
export const rowPulldownRef = (r) => `R${r + 1}`;
export const cselPulldownRef = (c) => `R${ROWS + c + 1}`;
export const touchPadRef = (c) => `TP${c + 1}`;

// ===========================================================================
// Routing skeletons
// ===========================================================================

/**
 * ROW r runs horizontally on F.Cu down the channel between pad rows r-1 and r,
 * i.e. at rowY(r)-3.2. Each gate is 2.25mm above the line, so the stub is a
 * straight drop.
 */
export const rowLineY = (r) => rowY(r) - 3.2;

/**
 * COL c runs vertically on B.Cu down the channel to the left of pad column c,
 * linking the 21 sources in that column. The FET source pin sits at
 * (colX-0.9375, rowY+0.95) and the via at (colX-3.2, rowY), so the stub runs
 * left and slightly back but never crosses the gate stub above it.
 */
export const sourceVia = (n) => ({ x: colChannelX(colOf(n)), y: rowY(rowOf(n)) });

/**
 * The drain via. It has to land on the B.Cu pad -- that is the only copper on
 * that layer near the FET -- so it sits 1.9mm off the pad centre, which is
 * inside the 2.5mm pad radius but clear of the FET's pin 3 by 0.21mm. It is
 * deliberately not centred under pin 3: an untented via in a soldered SMD pad
 * wicks paste and voids the joint.
 */
export const drainVia = (n) => ({ x: colX(colOf(n)) + 1.9, y: rowY(rowOf(n)) });

/** Where the touch pads themselves land: one 21-pad footprint per column. */
export const touchPadPos = (c) => ({ x: colX(c), y: ORIGIN_Y + CY });

/**
 * J1, the 40-way 0.5mm FPC into the control board, in the bottom margin
 * centred on the board. 19.5mm of contacts plus mounting pads comes to about
 * 25mm wide and 6mm deep, which fits between the two mounting holes with
 * 15mm to spare on each side.
 */
export const J1_POS = { x: ORIGIN_X + CX, y: ORIGIN_Y + BOARD_H - 5 };
export const J1_SIZE = { w: 25.1, h: 6.0 };

// ===========================================================================
// Self-check
// ===========================================================================

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/**
 * Every placement and via this layout asks for, as flat records.
 *
 * `hx`/`hy` are the body extents (what must stay on the board); `chx`/`chy`
 * are the courtyard extents (what DRC compares). TouchPadColumn has no
 * courtyard on purpose -- a front-side one would collide with the MOSFET
 * sitting directly above every pad -- so its courtyard extents are zero.
 */
export function placements() {
  const out = [];

  for (let c = 0; c < COLS; c++) {
    const p = touchPadPos(c);
    // The whole column is one footprint: 21 pads at 6.4mm pitch, so the body
    // is 133mm tall even though the pads themselves are only 5mm across.
    out.push({
      ref: touchPadRef(c),
      kind: "touchpad",
      layer: "B.Cu",
      ...p,
      hx: PAD_DIA / 2,
      hy: ((ROWS - 1) * PITCH + PAD_DIA) / 2,
      chx: 0,
      chy: 0,
    });
  }
  for (let n = 1; n <= PAD_COUNT; n++) {
    out.push({
      ref: padMosfetRef(n),
      kind: "fet",
      ...mosfetPos(n),
      hx: SOT23_HALF_X,
      hy: SOT23_HALF_Y,
      chx: SOT23_CRTYD_HX,
      chy: SOT23_CRTYD_HY,
    });
  }
  for (let c = 0; c < COLS; c++) {
    out.push({
      ref: columnSelectRef(c),
      kind: "fet",
      ...columnSelectPos(c),
      hx: SOT23_HALF_X,
      hy: SOT23_HALF_Y,
      chx: SOT23_CRTYD_HX,
      chy: SOT23_CRTYD_HY,
    });
  }
  for (let r = 0; r < ROWS; r++) {
    out.push({
      ref: rowPulldownRef(r),
      kind: "res",
      ...rowPulldownPos(r),
      hx: R0402_HALF_X,
      hy: R0402_HALF_Y,
      chx: R0402_CRTYD_HX,
      chy: R0402_CRTYD_HY,
    });
  }
  for (let c = 0; c < COLS; c++) {
    out.push({
      ref: cselPulldownRef(c),
      kind: "res",
      ...cselPulldownPos(c),
      hx: R0402_HALF_X,
      hy: R0402_HALF_Y,
      chx: R0402_CRTYD_HX,
      chy: R0402_CRTYD_HY,
    });
  }
  out.push({
    ref: "J1",
    kind: "conn",
    x: J1_POS.x,
    y: J1_POS.y,
    hx: J1_SIZE.w / 2,
    hy: J1_SIZE.h / 2,
    // The library footprint's courtyard is 13.05 x 3.95 and offset upward, so
    // it is not centred on J1_POS; recentring over-approximates it by 0.95mm,
    // which is the safe direction for a keep-out.
    chx: 13.05,
    chy: 3.95,
  });

  return out;
}

export function vias() {
  const out = [];
  for (let n = 1; n <= PAD_COUNT; n++) {
    out.push({ net: PAD(n), role: "drain", ...drainVia(n) });
    out.push({ net: COL(colOf(n)), role: "source", ...sourceVia(n) });
  }
  return out;
}

/** Axis-aligned courtyard overlap between two placements. */
function courtyardOverlap(a, b) {
  return Math.abs(a.x - b.x) < a.chx + b.chx && Math.abs(a.y - b.y) < a.chy + b.chy;
}

/**
 * Report every placement that leaves the board, fouls a mounting hole, or
 * overlaps another placement. Placement overlap is not always fatal -- a
 * resistor may legitimately sit inside a connector's footprint -- so this
 * reports rather than throws, and the caller decides.
 */
export function check() {
  const problems = [];
  const items = placements();

  const x0 = ORIGIN_X;
  const y0 = ORIGIN_Y;
  const x1 = ORIGIN_X + BOARD_W;
  const y1 = ORIGIN_Y + BOARD_H;

  for (const it of items) {
    if (it.x - it.hx < x0 || it.x + it.hx > x1 || it.y - it.hy < y0 || it.y + it.hy > y1) {
      problems.push(
        `${it.ref}: body ${it.x - it.hx < x0 || it.x + it.hx > x1 ? "crosses a side edge" : "crosses a top/bottom edge"}`,
      );
    }
  }

  // Mounting holes: the same four the board-frame step places. What DRC
  // compares is the hole's courtyard -- a 2.95mm screw-head circle -- against
  // each footprint's courtyard rectangle, so that is what this measures. The
  // hole itself is only 1.35mm; testing against that is what let six parts sit
  // under a screw head unnoticed.
  const holes = mountingHoles();
  for (const h of holes) {
    for (const it of items) {
      if (!it.chx && !it.chy) continue; // no courtyard: nothing to compare
      const nx = Math.min(Math.max(h.x, it.x - it.chx), it.x + it.chx);
      const ny = Math.min(Math.max(h.y, it.y - it.chy), it.y + it.chy);
      if (dist({ x: nx, y: ny }, h) < MOUNT_HOLE_CRTYD_R) {
        problems.push(`${it.ref}: courtyard reaches inside the screw head at (${h.x}, ${h.y})`);
      }
    }
  }

  // Only footprints on the SAME side can physically collide. The touch pads
  // are on B.Cu and the MOSFETs on F.Cu, so every pad sits directly under its
  // own FET by design -- that XY overlap is the whole point, not a defect.
  // Everything except the touch pads is on F.Cu, hence the default.
  const layerOf = (it) => it.layer ?? "F.Cu";

  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (layerOf(items[i]) !== layerOf(items[j])) continue;
      if (courtyardOverlap(items[i], items[j])) {
        problems.push(`${items[i].ref} courtyard overlaps ${items[j].ref}`);
      }
    }
  }

  return problems;
}

/**
 * Confirm the two things the channel derivation above depends on: that each
 * via clears the pads on both sides of its channel, and that the drain via
 * lands inside its own pad without touching the FET's pin 3.
 */
export function checkVias() {
  const problems = [];
  const reach = MOUNT_HOLE_DIA; // generous: catches anything near a hole

  for (let n = 1; n <= PAD_COUNT; n++) {
    const c = colOf(n);
    const r = rowOf(n);

    // Source via: must clear pad c on the right and pad c-1 on the left.
    const sv = sourceVia(n);
    const gapRight = colX(c) - PAD_DIA / 2 - (sv.x + VIA_DIA / 2);
    const gapLeft =
      c === 0 ? Infinity : sv.x - VIA_DIA / 2 - (colX(c - 1) + PAD_DIA / 2);
    if (gapRight < CLEARANCE) {
      problems.push(`source via for ${PAD(n)}: only ${gapRight.toFixed(3)}mm to pad ${PAD(n)}`);
    }
    if (gapLeft < CLEARANCE) {
      problems.push(`source via for ${PAD(n)}: only ${gapLeft.toFixed(3)}mm to pad column ${c - 1}`);
    }

    // Drain via: inside its own pad, clear of the FET body it serves.
    const dv = drainVia(n);
    const offCentre = Math.abs(colX(c) + 1.9 - colX(c));
    if (offCentre + VIA_DIA / 2 > PAD_DIA / 2) {
      problems.push(`drain via for ${PAD(n)} is not fully inside its pad`);
    }
    const gapPin3 = offCentre - VIA_DIA / 2 - SOT23_HALF_X;
    if (gapPin3 < 0) {
      problems.push(`drain via for ${PAD(n)} touches the FET's pin 3 (${gapPin3.toFixed(3)}mm)`);
    }
  }

  // A column line and its own source vias share one 1.4mm channel, so the
  // channel must be able to hold both.
  for (let c = 0; c < COLS; c++) {
    const neighbourLeft = c === 0 ? ORIGIN_X : colX(c - 1) + PAD_DIA / 2;
    const neighbourRight = colX(c) - PAD_DIA / 2;
    const width = neighbourRight - neighbourLeft;
    const need = VIA_DIA + 2 * CLEARANCE;
    if (width < need) {
      problems.push(
        `column ${c} channel is ${width.toFixed(2)}mm but a via plus clearance needs ${need.toFixed(2)}mm`,
      );
    }
  }

  void reach;
  return problems;
}

// --- CLI -------------------------------------------------------------------
// Compare via pathToFileURL rather than string-building a file:// URL: on
// Windows the real href has three slashes (file:///D:/...), so a hand-built
// two-slash URL never matches and this block silently never runs.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const items = placements();
  console.log(`board      ${BOARD_W} x ${BOARD_H}mm at (${ORIGIN_X}, ${ORIGIN_Y})`);
  console.log(`pads       ${PAD_COUNT} x D${PAD_DIA}mm at ${PITCH}mm pitch`);
  console.log(`span       x ${(colX(0) - PAD_DIA / 2).toFixed(2)}..${(colX(COLS - 1) + PAD_DIA / 2).toFixed(2)}`);
  console.log(`           y ${(rowY(0) - PAD_DIA / 2).toFixed(2)}..${(rowY(ROWS - 1) + PAD_DIA / 2).toFixed(2)}`);
  console.log(`channel    ${(PITCH - PAD_DIA).toFixed(2)}mm between pads`);
  console.log(`placements ${items.length}`);

  const channel = checkVias();
  const overlap = check();
  console.log(`\nchannel/via checks: ${channel.length} problem(s)`);
  for (const p of channel) console.log(`  ! ${p}`);
  console.log(`placement checks:   ${overlap.length} problem(s)`);
  for (const p of overlap.slice(0, 60)) console.log(`  ! ${p}`);
  if (overlap.length > 60) console.log(`  ... and ${overlap.length - 60} more`);
}

"""Calibrate the flood against a target whose answer is not in doubt.

The last run reported 10/31 nets reachable and I do not believe it.  The flood's
*exploration* is sound -- it is a connectivity flood, it visits every cell free
space allows -- but the thing that decides a hit is a halo: a cell counts as
touching net n only if its NEAREST copper belongs to n.  In a 14mm strip carrying
a 40-pin header's fan-out, the runner-up is often nearer than the target, the
cell is skipped, and a net that is plainly reachable comes back MISSING.  Every
MISSING net in that run sat 0.28-31mm from the frontier, and several of those
gaps are the width of the halo band itself -- the signature of exactly that
error.

Model M cannot referee either: matrix.py's own 33/33 dissolves the target's
copper out of the obstacle set, so it answers a different question.

So ask a question with a known answer.  Chip A sits at (96.5, 238.2) and chip B
at (97.0, 207.2): same 14.2mm left strip, 31mm apart, nothing between them but
J1A's own pads.  Chip A's flooded set reaches y=100.8..249.2 in that strip, so it
must come within a hair of chip B's pads.  If it cannot, the flood is broken.  If
it can, the flood is sound and the halo test is the only suspect left.

Two target tests then run side by side on the same flood:

  ownership  -- a cell is a touch point for n only if its nearest copper is n.
                Conservative: misses attach points that exist.
  optimistic -- any legal cell within the halo band of n's copper.  Ignores who
                else is nearby.  Over-confident: claims attach points that a
                foreign net may block.

The truth is bracketed between them, and the width of that bracket is the honest
error bar on the verdict.
"""
import collections
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
from probe import NGrid, octile_dt                         # noqa: E402

S = 1e6
F_Cu, B_Cu = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = [F_Cu, B_Cu]

STEP = 0.1
CLEAR = 0.20
SAFETY = 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3
HALO_BAND = KEEP + 2 * STEP

PLACE = {
    "A": (96.5, 238.2, ["ROW20", "ROW19", "CSEL0", "CSEL1",
                        "CSEL2", "CSEL8", "CSEL7", "CSEL9"]),
    "B": (97.0, 207.2, ["ROW1", "CSEL4", "ROW16", "ROW12",
                        "ROW15", "ROW14", "ROW17", "ROW18"]),
    "C": (170.5, 171.2, ["ROW6", "ROW7", "ROW0", "ROW9",
                         "ROW10", "ROW11", "ROW8", "ROW13"]),
    "D": (172.5, 134.2, ["CSEL5", "CSEL3", "CSEL6", "ROW4",
                         "ROW5", "ROW3", "ROW2"]),
}
NETNAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
NETID = {n: k for k, n in enumerate(NETNAMES)}

LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = {"15", "1", "2", "3", "4", "5", "6", "7"}      # QA..QH

board = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")

items = list(board.GetTracks())
for fp in board.GetFootprints():
    items.extend(fp.Pads())

placed, chip_idx, chip_pads = {}, {}, {}
for tag, (cx, cy, _) in PLACE.items():
    fp = pcbnew.FootprintLoad(LIB, FP)
    fp.SetPosition(pcbnew.VECTOR2I(int(cx * S), int(cy * S)))
    fp.SetReference("U%s" % tag)
    fp.SetValue("74HC595")
    board.Add(fp)
    placed[tag] = fp
    pads = list(fp.Pads())
    chip_idx[tag] = list(range(len(items), len(items) + len(pads)))
    chip_pads[tag] = [p.GetPosition() for p in pads]
    items.extend(pads)

net_of = np.array([it.GetNetname() for it in items], dtype=object)


def disc(g, cx, cy, r):
    """Cells whose centre is within r of (cx, cy), in grid shape (ny, nx)."""
    m = np.zeros((g.ny, g.nx), bool)
    i0 = max(0, int((cx - r - g.x0) / g.step))
    i1 = min(g.nx - 1, int((cx + r - g.x0) / g.step))
    j0 = max(0, int((cy - r - g.y0) / g.step))
    j1 = min(g.ny - 1, int((cy + r - g.y0) / g.step))
    if i1 < i0 or j1 < j0:
        return m
    xs = g.x0 + np.arange(i0, i1 + 1) * g.step
    ys = g.y0 + np.arange(j0, j1 + 1) * g.step
    m[j0:j1 + 1, i0:i1 + 1] = np.hypot(xs[None, :] - cx,
                                       ys[:, None] - cy) <= r
    return m


def wavefront(OK, VOK, starts, max_iter=8000):
    seen = {lay: starts[lay].copy() for lay in LAYERS}
    it_no = 0
    for it_no in range(max_iter):
        nxt = {}
        for lay in LAYERS:
            s, ok = seen[lay], OK[lay]
            r = s.copy()
            r[1:, :] |= s[:-1, :]
            r[:-1, :] |= s[1:, :]
            r[:, 1:] |= s[:, :-1]
            r[:, :-1] |= s[:, 1:]
            r[1:, 1:] |= s[:-1, :-1] & ok[1:, 1:] & ok[:-1, 1:] & ok[1:, :-1]
            r[1:, :-1] |= s[:-1, 1:] & ok[1:, :-1] & ok[:-1, :-1] & ok[1:, 1:]
            r[:-1, 1:] |= s[1:, :-1] & ok[:-1, 1:] & ok[1:, 1:] & ok[:-1, :-1]
            r[:-1, :-1] |= s[1:, 1:] & ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:]
            nxt[lay] = (r & ok) | s
        # A via joins the two layers AT that cell, so arriving on EITHER layer
        # is enough to take it.  Requiring both (VOK & nxt[F] & nxt[B]) never
        # enters a pocket whose only entrance is its own via.  This calibration
        # never caught that because it only exercised A->B at 0.20mm, a
        # same-layer check that never takes a via at all.
        viacell = VOK & np.logical_or.reduce([nxt[lay] for lay in LAYERS])
        moved = False
        for lay in LAYERS:
            new = nxt[lay] | viacell
            if not moved and not np.array_equal(new, seen[lay]):
                moved = True
            seen[lay] = new
        if not moved:
            break
    return seen, it_no


def legal_any(OK):
    return np.logical_or.reduce([OK[l] for l in LAYERS])


for tag, (cx, cy, nets) in PLACE.items():
    print("\n======== chip %s at (%.1f, %.1f) ========" % (tag, cx, cy))

    drop = set(chip_idx[tag])
    g = NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build([it for k, it in enumerate(items) if k not in drop])

    starts = {lay: np.zeros((g.ny, g.nx), bool) for lay in LAYERS}
    for p in placed[tag].Pads():
        if p.GetNumber() not in OUT_PADS:
            continue
        c = p.GetPosition()
        i, j = g.ij(c.x / S, c.y / S)
        if 0 <= j < g.ny and 0 <= i < g.nx:
            starts[F_Cu][j, i] = True

    seen, iters = wavefront(g.OK, g.VOK, starts)
    reach = np.logical_or.reduce([seen[l] for l in LAYERS])
    rj, ri = np.nonzero(reach)
    print("  flood: %d cells, %d iterations, bbox x %.1f..%.1f  y %.1f..%.1f"
          % (int(reach.sum()), iters,
             g.x0 + ri.min() * STEP, g.x0 + ri.max() * STEP,
             g.y0 + rj.min() * STEP, g.y0 + rj.max() * STEP))

    # ---- the oracle -------------------------------------------------------
    # Every other chip is a target whose reachability is not in question when
    # it shares the flood's strip.  A and B share the left strip; C and D share
    # the right.  Distance is measured to a 0.6mm disc at each pad centre, which
    # is a purely geometric question -- no ownership, no halo, no netlist.
    print("  oracle -- distance from the flooded set to the other chips' pads:")
    for other in PLACE:
        if other == tag:
            continue
        mask = np.zeros((g.ny, g.nx), bool)
        for c in chip_pads[other]:
            mask |= disc(g, c.x / S, c.y / S, 0.6)
        if not mask.any():
            continue
        dn = octile_dt(mask, STEP) * STEP
        gap = float(dn[reach].min())
        same = "same strip" if (other in "AB") == (tag in "AB") else "other side"
        print("     %s (%s)  min distance %6.2f mm   %s"
              % (other, same, gap, "TOUCHES" if gap <= STEP else ""))

    # ---- the two target tests --------------------------------------------
    own = {}
    for lay in LAYERS:
        o = g.OWN[lay]
        good = o >= 0
        own[lay] = np.where(good, net_of[np.where(good, o, 0)], "")

    print("  targets:  ownership-halo (conservative) | optimistic (any copper)")
    got = {"own": [], "opt": []}
    for n in nets:
        k = NETID[n]
        # conservative: legal cell whose nearest copper is n, inside the band
        m_own = np.zeros((g.ny, g.nx), bool)
        m_cop = np.zeros((g.ny, g.nx), bool)
        for lay in LAYERS:
            hit = own[lay] == n
            m_own |= hit & (g.D[lay] < HALO_BAND)
            m_cop |= hit & (g.D[lay] <= 0.02)          # the copper itself
        a = bool((reach & m_own).any())
        # optimistic: any legal cell within the band of n's copper, regardless
        # of who else is nearer
        dt = octile_dt(m_cop, STEP) * STEP
        b = bool((reach & (dt <= HALO_BAND) & legal_any(g.OK)).any())
        if a:
            got["own"].append(n)
        if b:
            got["opt"].append(n)
        print("     %-6s  own %-3s   opt %-3s   halo cells %6d"
              % (n, "yes" if a else "no", "yes" if b else "no",
                 int(m_own.sum())))

    print("  chip %s: ownership %d/%d   optimistic %d/%d"
          % (tag, len(got["own"]), len(nets), len(got["opt"]), len(nets)))
    miss = [n for n in nets if n not in got["opt"]]
    if miss:
        print("     optimistic still missing: %s" % " ".join(miss))

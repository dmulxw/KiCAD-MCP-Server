"""The placement-independent question: which nets can a chip reach from where?

_tp_reach.py and _tp_cal.py both flooded from the four sites _tp_place.py chose,
and both came back negative -- 10/31, verified against an oracle that needs no
netlist to be trusted.  But "these four sites fail" and "the pivot is impossible"
are different claims, and only the second one is worth acting on.

The difference is that a chip can sit at any of several hundred legal sites
(_tp_place.py's SITES), and the reachable set from a site is fixed by geometry
alone -- it does not depend on which site the assignment solver happened to pick.
So label the free space ONCE, into connected components.  Then:

  * a net lives in the components that touch its copper;
  * a site lives in the component its output pads can step onto;
  * the site serves the net exactly when those component sets intersect.

That turns 31 floods into one labelling pass, and it answers for all sites at
once rather than for one guessed assignment.

Connectivity is the same model the floods used: 8-connected within a layer, a
diagonal only when both orthogonal neighbours are legal, and the two layers
joined wherever a via is legal.  As a check against the floods already run, the
seed sets from chips A/B/C/D are re-run here and each must land in exactly one
component -- and A and B, 31mm apart in the same strip, must land in the SAME
one, since the calibration measured only 0.20mm between them.
"""
import json
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
from probe import NGrid                                   # noqa: E402
from _tp_label import label_free                          # noqa: E402

S = 1e6
F_Cu, B_Cu = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = [F_Cu, B_Cu]

STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3
HALO_BAND = KEEP + 2 * STEP

NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
NETID = {n: k for k, n in enumerate(NAMES)}
CAP = 8

LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = ["15", "1", "2", "3", "4", "5", "6", "7"]      # QA..QH

PLACE = {"A": (96.5, 238.2), "B": (97.0, 207.2),
         "C": (170.5, 171.2), "D": (172.5, 134.2)}

board = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")

# No chips on the board.  A component is a property of the existing copper; a
# chip's own pads are where a route starts, not an obstacle to itself.
g = NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
items = list(board.GetTracks())
for fp in board.GetFootprints():
    items.extend(fp.Pads())
g.build(items)
print("grid %d x %d per layer, %.1fM cells" % (g.ny, g.nx, g.ny * g.nx * 2 / 1e6))

# ---------------------------------------------------------------- labelling


comp, K = label_free(g.OK, g.VOK, LAYERS, g.nx, g.ny)
print("components: %d" % K)

size = np.bincount(np.concatenate([comp[l][comp[l] >= 0] for l in LAYERS]), minlength=K)
order = np.argsort(-size)
print("largest components (cells, mm^2 at 0.01mm^2/cell):")
for k in order[:8]:
    print("   #%-5d %9d cells  %8.1f mm2" % (k, size[k], size[k] * STEP * STEP))


def seeds_from_pads(cx, cy, r=1.0):
    """Legal F.Cu cells a route can step onto from an output pad centre.

    The pad is copper; the route leaves it on F.Cu, so only F.Cu cells count.
    An SMD pad cannot via in place -- a via there would be unconnected copper.
    """
    got = set()
    for n in OUT_PADS:
        dx, dy = PADOFF[n]
        px, py = cx + dx, cy + dy
        i0 = max(0, int((px - r - g.x0) / STEP))
        i1 = min(g.nx - 1, int((px + r - g.x0) / STEP))
        j0 = max(0, int((py - r - g.y0) / STEP))
        j1 = min(g.ny - 1, int((py + r - g.y0) / STEP))
        if i1 < i0 or j1 < j0:
            continue
        xs = g.x0 + np.arange(i0, i1 + 1) * STEP
        ys = g.y0 + np.arange(j0, j1 + 1) * STEP
        near = np.hypot(xs[None, :] - px, ys[:, None] - py) <= r
        m = near & g.OK[F_Cu][j0:j1 + 1, i0:i1 + 1]
        if m.any():
            got.update(np.unique(comp[F_Cu][j0:j1 + 1, i0:i1 + 1][m]).tolist())
    got.discard(-1)
    return got


fp0 = pcbnew.FootprintLoad(LIB, FP)
PADOFF = {}
for p in fp0.Pads():
    n = p.GetNumber()
    if n in OUT_PADS:
        c = p.GetPosition()
        PADOFF[n] = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))
print("\noutput pad offsets (mm):")
print("   " + "  ".join("%s(%+.2f,%+.2f)" % (n, PADOFF[n][0], PADOFF[n][1])
                        for n in OUT_PADS))

# ---- check the labelling against the floods that were already run ----------
print("\nvalidation -- the four seeded sites must each land in ONE component,")
print("and A and B, 31mm apart in the same strip and 0.20mm apart per the")
print("calibration, must land in the SAME one:")
FLOOD = {"A": 122288, "B": 122338, "C": 58967, "D": 22371}
site_comp = {}
for tag, (cx, cy) in PLACE.items():
    s = seeds_from_pads(cx, cy)
    site_comp[tag] = s
    sz = [int(size[k]) for k in s if 0 <= k < K]
    print("   chip %s at (%.1f, %.1f)  ->  components %s   %s"
          % (tag, cx, cy, sorted(s), "OK" if len(s) == 1 else "SPLIT!"))
    print("        component sizes %s   (the wavefront found %d cells for %s)"
          % (sz, FLOOD[tag], tag))
print("   A and B same component: %s"
      % ("YES" if site_comp["A"] == site_comp["B"] else "NO"))
print("   C and D same component: %s"
      % ("YES" if site_comp["C"] == site_comp["D"] else "NO"))

# ---- and directly against the wavefront, on this grid ---------------------
# Two independent methods for the same claim.  If they disagree, the labelling
# is wrong and every number below it inherits the error, so settle it here.
LAB = sorted(site_comp["A"])[0] if site_comp["A"] else None
if LAB is not None:
    st = {lay: np.zeros((g.ny, g.nx), bool) for lay in LAYERS}
    for n in OUT_PADS:
        dx, dy = PADOFF[n]
        i, j = g.ij(96.5 + dx, 238.2 + dy)
        if 0 <= j < g.ny and 0 <= i < g.nx and g.OK[F_Cu][j, i]:
            st[F_Cu][j, i] = True
    seen = {lay: st[lay].copy() for lay in LAYERS}
    for _ in range(20000):
        nxt = {}
        for lay in LAYERS:
            s, ok = seen[lay], g.OK[lay]
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
        # A via at a cell joins the two layers there, so arriving on EITHER
        # layer is enough to take it.  The earlier floods wrote this as
        # VOK & nxt[F] & nxt[B] -- waiting for both -- which never crosses into
        # a pocket whose only entrance is its own via, and is why they came back
        # at 10/31 with the frontier stopping dead against open copper.
        vc = g.VOK & np.logical_or.reduce([nxt[lay] for lay in LAYERS])
        moved = False
        for lay in LAYERS:
            new = nxt[lay] | vc
            if not np.array_equal(new, seen[lay]):
                moved = True
            seen[lay] = new
        if not moved:
            break
    flood = np.logical_or.reduce([seen[l] for l in LAYERS])
    lab = np.logical_or.reduce([comp[l] == LAB for l in LAYERS])
    print("\ncross-check on this grid, seed = chip A's output pads:")
    print("   wavefront %d cells   labelling %d cells   both %d"
          % (int(flood.sum()), int(lab.sum()), int((flood & lab).sum())))
    print("   flood-only %d   label-only %d   -> %s"
          % (int((flood & ~lab).sum()), int((lab & ~flood).sum()),
             "AGREE" if not (lab & ~flood).any() and not (flood & ~lab).any()
             else "DISAGREE"))
    if (lab & ~flood).any():
        j, i = np.nonzero(lab & ~flood)
        print("   labelling reaches cells the flood does not, e.g. x %.1f y %.1f"
              % (g.x0 + i[0] * STEP, g.y0 + j[0] * STEP))

# ---- which components touch each net's copper ------------------------------
own = {}
for lay in LAYERS:
    o = g.OWN[lay]
    own[lay] = np.where(o >= 0, np.array([it.GetNetname() for it in items],
                                         dtype=object)[np.where(o >= 0, o, 0)], "")

net_comp = {n: set() for n in NAMES}
for lay in LAYERS:
    for n in NAMES:
        m = (own[lay] == n) & (g.D[lay] < HALO_BAND) & (comp[lay] >= 0)
        if m.any():
            net_comp[n].update(np.unique(comp[lay][m]).tolist())

# ---- the sites -------------------------------------------------------------
# The per-net verdict above stands on its own: if a net's component contains no
# site at all, the pivot is impossible whatever the four sites are.  The site
# sweep only sharpens that into "which four", so it is allowed to be absent.
ALL = None
for src in ("_tp_places.json", "_tp_place.json"):
    try:
        ALL = json.load(open(src))["all_sites"]
        print("\nlegal sites from %s: %d" % (src, len(ALL)))
        break
    except (IOError, KeyError):
        continue
if ALL is None:
    print("\n(no all_sites in _tp_places.json or _tp_place.json"
          " -- skipping the four-site search)")
    raise SystemExit(0)
print("\nlegal sites: %d" % len(ALL))

site_of = {}
for si, (side, cx, cy) in enumerate(ALL):
    s = seeds_from_pads(cx, cy)
    if s:
        site_of[si] = s

M = np.zeros((len(NAMES), len(ALL)), bool)
for r, n in enumerate(NAMES):
    for si, s in site_of.items():
        if net_comp[n] & s:
            M[r, si] = True

print("\nper-net: how many of the %d sites can reach it" % len(ALL))
dead = []
for r, n in enumerate(NAMES):
    k = int(M[r].sum())
    if k == 0:
        dead.append(n)
    print("   %-6s  %4d sites   components %s"
          % (n, k, sorted(net_comp[n])[:6]))
print("\nnets no site can reach: %s"
      % (" ".join(dead) if dead else "none"))

# ---- can four sites cover all 31, eight nets each? -------------------------
covered = set()
chosen = []
for _ in range(4):
    best, bestc = None, -1
    for si in site_of:
        if si in [c[0] for c in chosen]:
            continue
        c = len([r for r in range(len(NAMES))
                 if M[r, si] and NAMES[r] not in covered])
        if c > bestc:
            bestc, best = c, si
    if best is None or bestc <= 0:
        break
    gained = [NAMES[r] for r in range(len(NAMES))
              if M[r, best] and NAMES[r] not in covered]
    covered.update(gained[:CAP])
    chosen.append((best, ALL[best], len(gained)))
    print("\ngreedy pick: site %d %s at (%.1f, %.1f)  covers %d new nets"
          % (best, ALL[best][0], ALL[best][1], ALL[best][2], len(gained)))
    print("   capacity 8, so takes: %s" % " ".join(gained[:CAP]))
    if len(gained) > CAP:
        print("   (drops: %s)" % " ".join(gained[CAP:]))

un = [n for n in NAMES if n not in covered]
print("\n================ coverage ================")
print("  greedy best 4 sites cover %d/%d nets" % (len(covered), len(NAMES)))
if un:
    print("  UNCOVERED: %s" % " ".join(un))

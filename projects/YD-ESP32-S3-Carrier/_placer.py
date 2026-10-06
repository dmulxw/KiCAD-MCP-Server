"""Where can R6-R9 actually go?

The four pull resistors were dropped at y=20, x=48..66 straight onto the board's
45-degree power corridor: R7 straddles the +3V3 diagonal through (58.2,25.4)-
(43.6,10.8), R9 straddles the 1.00mm +5V vertical at x=66.8.  That is six of the
43 violations and no router can fix them -- a shorted pad is a shorted pad.
DRC says only R7 and R9 are actually affected; R6/R8 are clean.

Scan for positions where a 0603 (rot 90: pads 0.80x0.95 at y +-0.825) clears every
foreign trace and pad on BOTH layers by a margin, preferring the smallest move.

Traces are capsules (segment + width/2), so the distance is segment-to-rect --
a bbox test calls a 34mm diagonal 24x24mm of solid copper and reports -11mm for a
part that is provably clean.

    python _placer.py [--margin 0.30] [--maxmove 3.0] [--only R7,R9]
"""
import argparse

import pcbnew

S = 1e6
REF = ("R6", "R7", "R8", "R9")
PAD_DX, PAD_DY = 0.80, 0.95
PAD_OFF = 0.825
CLEAR = 0.16                     # the board's track clearance rule

ap = argparse.ArgumentParser()
ap.add_argument("--margin", type=float, default=0.30)
ap.add_argument("--maxmove", type=float, default=3.0)
ap.add_argument("--step", type=float, default=0.05)
ap.add_argument("--only", default="")
A = ap.parse_args()

board = pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb")


def seg_pt(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def seg_seg(a, b, c, d):
    """Min distance between segments ab and cd (0 if they cross)."""
    return min(seg_pt(c[0], c[1], d[0], d[1], a[0], a[1]),
               seg_pt(c[0], c[1], d[0], d[1], b[0], b[1]),
               seg_pt(a[0], a[1], b[0], b[1], c[0], c[1]),
               seg_pt(a[0], a[1], b[0], b[1], d[0], d[1]))


# ---- copper as capsules -----------------------------------------------------
caps = []                        # (ax, ay, bx, by, radius, net, layer, bbox)
for t in board.GetTracks():
    if t.Type() != pcbnew.PCB_TRACE_T:
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = a.x / S, a.y / S, b.x / S, b.y / S
    r = t.GetWidth() / S / 2
    caps.append((ax, ay, bx, by, r, t.GetNetname(), t.GetLayerName(), t.GetLayer(),
                 (min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)))

# (cx, cy, hx, hy, net, ref, on_f, on_b).  An SMD pad carries copper on ONE
# layer only: treating it as two-sided invents clearance violations against the
# opposite layer's traces -- e.g. IO43's B.Cu stubs under R6's F.Cu pad.
pads = []
for f in board.GetFootprints():
    for p in f.Pads():
        c, sz = p.GetPosition(), p.GetSize()
        pads.append((c.x / S, c.y / S, sz.x / S / 2, sz.y / S / 2,
                     p.GetNetname(), f.GetReference(),
                     p.IsOnLayer(pcbnew.F_Cu), p.IsOnLayer(pcbnew.B_Cu)))

own = {f.GetReference(): {p.GetNumber(): p.GetNetname() for p in f.Pads()}
       for f in board.GetFootprints() if f.GetReference() in REF}
print("own nets: %s" % own, flush=True)

RECT_EDGES = ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1))


def pad_clearance(cx, cy, ignore, others, layers):
    """min (copper clearance) over the two pads of a rot-90 0603 at cx,cy.

    `layers` is the set of board layers this candidate's pads occupy; copper on
    any other layer is invisible to it.
    """
    worst, who = 1e9, None
    for off in (-PAD_OFF, PAD_OFF):
        ox, oy = cx, cy + off
        x0, y0 = ox - PAD_DX / 2, oy - PAD_DY / 2
        x1, y1 = ox + PAD_DX / 2, oy + PAD_DY / 2
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        edges = [((ox + ex0 * PAD_DX / 2, oy + ey0 * PAD_DY / 2),
                  (ox + ex1 * PAD_DX / 2, oy + ey1 * PAD_DY / 2))
                 for ex0, ey0, ex1, ey1 in RECT_EDGES]
        pad_cxx = (x0 + x1) / 2
        for ax, ay, bx, by, r, net, lay, lid, bb in caps:
            if net in ignore or lid not in layers:
                continue
            if bb[0] > x1 + r + 1.0 or bb[2] < x0 - r - 1.0 \
               or bb[1] > y1 + r + 1.0 or bb[3] < y0 - r - 1.0:
                continue
            d = seg_seg((ax, ay), (bx, by), *edges[0])
            for e in edges[1:]:
                d = min(d, seg_seg((ax, ay), (bx, by), *e))
            for px, py in corners:
                d = min(d, seg_pt(ax, ay, bx, by, px, py))
            # a segment with both ends inside the rect: corners are the inside
            # points, so d is already 0 for a crossing
            g = d - r
            if g < worst:
                worst, who = g, "%s/%s" % (net or "-", lay or "-")
        for px, py, hx, hy, net, ref, on_f, on_b in pads:
            if net in ignore or ref == target:
                continue
            if not ((on_f and pcbnew.F_Cu in layers) or (on_b and pcbnew.B_Cu in layers)):
                continue
            if px - hx > x1 + 1.0 or px + hx < x0 - 1.0 \
               or py - hy > y1 + 1.0 or py + hy < y0 - 1.0:
                continue
            g = max(abs(px - pad_cxx) - hx - PAD_DX / 2,
                    abs(py - oy) - hy - PAD_DY / 2)
            if g < worst:
                worst, who = g, "pad:%s(%s)" % (ref, net or "-")
        for ox2, oy2 in others:
            g = max(abs(ox2 - ox) - PAD_DX, abs(oy2 - oy) - PAD_DY)
            if g < worst:
                worst, who = g, "sibling"
    return worst, who


targets = [r for r in REF if not A.only or r in A.only.split(",")]
for target in targets:
    ign = {n for n in own[target].values() if n}
    others = [f.GetPosition() for f in board.GetFootprints()
              if f.GetReference() in REF and f.GetReference() != target]
    others = [(p.x / S, p.y / S) for p in others]
    cur = [f for f in board.GetFootprints() if f.GetReference() == target][0]
    cx0, cy0 = cur.GetPosition().x / S, cur.GetPosition().y / S
    layers = set()
    for p in cur.Pads():
        for lid in (pcbnew.F_Cu, pcbnew.B_Cu):
            if p.IsOnLayer(lid):
                layers.add(lid)
    cg, cw = pad_clearance(cx0, cy0, ign, others, layers)
    print("\n%s now (%.2f,%.2f)  clearance %.3f  [%s]"
          % (target, cx0, cy0, cg, cw), flush=True)

    best = []
    n = int(A.maxmove / A.step)
    for j in range(-n, n + 1):
        for i in range(-n, n + 1):
            cx, cy = cx0 + i * A.step, cy0 + j * A.step
            if ((cx - cx0) ** 2 + (cy - cy0) ** 2) ** 0.5 > A.maxmove:
                continue
            g, who = pad_clearance(cx, cy, ign, others, layers)
            if g >= A.margin:
                mv = ((cx - cx0) ** 2 + (cy - cy0) ** 2) ** 0.5
                best.append((mv, g, cx, cy, who))
    best.sort()
    for mv, g, cx, cy, who in best[:6]:
        print("   %.3fmm away -> (%.2f,%.2f)  clearance %.3f  [%s]"
              % (mv, cx, cy, g, who), flush=True)
    if not best:
        print("   nothing within %.1fmm clears %.2fmm" % (A.maxmove, A.margin),
              flush=True)

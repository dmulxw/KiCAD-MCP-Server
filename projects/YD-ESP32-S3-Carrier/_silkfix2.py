"""Re-place the reference fields the ESP32 socket move dragged onto copper.

_silkfix.py did this job for the 595 strip, with hand-picked anchors because the
strip is too tight to guess.  This is the same search driven off the footprint
instead: J1, J2, J8 and J10 slid as whole footprints, so their Reference fields
slid with them and J1.3/J1.4 and J2.3/J2.4 now sit under them -- silk_over_copper
-- while J10's landed on J8's silk -- silk_overlap.  Nothing here is electrical.

Anchors are generated from each footprint's own pad box, so this works for a
connector wherever it was moved to, and the search is the same one _silkfix.py
uses: slide the label out along a spiral and take the first position whose real
GetBoundingBox() clears every F.SilkS graphic, every F.Cu pad, every other
visible silk label, and the board edge.

    python _silkfix2.py <board.kicad_pcb> <out.kicad_pcb> REF[,REF...] [--dry-run]
"""
import sys

import pcbnew

S = 1e6
EDGE_M = 0.35          # silk to board outline
PAD_M = 0.06           # silk to exposed copper (silk_over_copper)
SILK_M = 0.06          # silk to silk
CELL = 2.0

args = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
BOARD, OUT = args[0], args[1]
REFS = args[2].split(",")

b = pcbnew.LoadBoard(BOARD)
if b is None:
    sys.exit("LoadBoard returned None for " + BOARD)


def rb(o):
    r = o.GetBoundingBox()
    return (r.GetLeft() / S, r.GetTop() / S, r.GetRight() / S, r.GetBottom() / S)


# ---- board outline ---------------------------------------------------
gx, gy = [], []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        q = rb(d)
        gx += [q[0], q[2]]
        gy += [q[1], q[3]]
BX0, BX1, BY0, BY1 = min(gx), max(gx), min(gy), max(gy)

MOVE = {(r, "Reference") for r in REFS}

# ---- obstacle index --------------------------------------------------
grid = {}


def add(bb, m):
    e = (bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m)
    for i in range(int(e[0] // CELL), int(e[2] // CELL) + 1):
        for j in range(int(e[1] // CELL), int(e[3] // CELL) + 1):
            grid.setdefault((i, j), []).append(e)


for fp in b.GetFootprints():
    ref = str(fp.GetReference())
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            add(rb(g), SILK_M)
    for p in fp.Pads():
        if p.IsOnLayer(pcbnew.F_Cu):
            add(rb(p), PAD_M)
    for nm, f in (("Reference", fp.Reference()), ("Value", fp.Value())):
        if f.IsVisible() and f.GetLayer() == pcbnew.F_SilkS and (ref, nm) not in MOVE:
            add(rb(f), SILK_M)
for d in b.GetDrawings():
    if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS:
        add(rb(d), SILK_M)
print("obstacles: %d boxes in %d cells" % (sum(len(v) for v in grid.values()),
                                           len(grid)))


def hits(bb):
    l, t, r, bo = bb
    if l < BX0 + EDGE_M or r > BX1 - EDGE_M:
        return True
    if t < BY0 + EDGE_M or bo > BY1 - EDGE_M:
        return True
    for i in range(int(l // CELL), int(r // CELL) + 1):
        for j in range(int(t // CELL), int(bo // CELL) + 1):
            for (ol, ot, orr, ob) in grid.get((i, j), ()):
                if l < orr and ol < r and t < ob and ot < bo:
                    return True
    return False


_CACHE = {}


def offsets(span, step):
    key = (span, step)
    if key not in _CACHE:
        n = int(span / step)
        o = [(i * step, j * step) for i in range(-n, n + 1) for j in range(-n, n + 1)]
        o.sort(key=lambda d: d[0] * d[0] + d[1] * d[1])
        _CACHE[key] = o
    return _CACHE[key]


def seek(obj, anchors, angles, span, step):
    """Nearest legal placement, or None (leaving the object untouched)."""
    home = (obj.GetPosition().x, obj.GetPosition().y, obj.GetTextAngleDegrees())
    offs = offsets(span, step)
    for (ax, ay) in anchors:
        for ang in angles:
            obj.SetTextAngleDegrees(ang)
            for (dx, dy) in offs:
                obj.SetPosition(pcbnew.VECTOR2I(int(round((ax + dx) * S)),
                                                int(round((ay + dy) * S))))
                bb = rb(obj)
                if not hits(bb):
                    add(bb, 0.0)          # reserve it so later labels avoid it
                    return (ax + dx, ay + dy, ang, bb)
    obj.SetPosition(pcbnew.VECTOR2I(home[0], home[1]))
    obj.SetTextAngleDegrees(home[2])
    return None


# ---- jobs ------------------------------------------------------------
# Anchors sit on a ring around the connector's own pads: west, east, north,
# south, at five stand-offs.  The search then slides each one to the nearest
# legal spot, so the connector's shape decides where its label can go rather
# than a number typed in here.
jobs = []
for fp in b.GetFootprints():
    ref = str(fp.GetReference())
    if ref not in REFS:
        continue
    xs, ys = [], []
    for p in fp.Pads():
        if not p.IsOnLayer(pcbnew.F_Cu):
            continue
        q = rb(p)
        xs += [q[0], q[2]]
        ys += [q[1], q[3]]
    if not xs:
        continue
    px0, px1, py0, py1 = min(xs), max(xs), min(ys), max(ys)
    pcx, pcy = (px0 + px1) / 2.0, (py0 + py1) / 2.0
    # Where the label is now comes first: it only landed on copper because the
    # footprint moved under it, so the nearest free spot is almost always a
    # short slide away, and a short slide keeps the label beside its own
    # connector's pin 1 instead of at mid-height.  The pad ring is the fallback
    # for the case where the current spot is walled in.
    anchors = [(fp.Reference().GetPosition().x / S,
                fp.Reference().GetPosition().y / S)]
    for d in (1.2, 2.0, 2.8, 3.6, 4.4):
        anchors += [(px0 - d, pcy), (px1 + d, pcy),
                    (pcx, py0 - d), (pcx, py1 + d)]
    jobs.append((ref, fp.Reference(), anchors))
    print("%-5s pads x %.2f..%.2f  y %.2f..%.2f" % (ref, px0, px1, py0, py1))

print("\n%-7s %-24s %s" % ("label", "was", "now"))
bad = []
for name, obj, anchors in jobs:
    before = (obj.GetPosition().x / S, obj.GetPosition().y / S)
    got = seek(obj, anchors, [0, 90], 4.0, 0.2)
    if got is None:
        bad.append(name)
        print("%-7s (%6.2f,%6.2f)              NO LEGAL SPOT" % (name, before[0], before[1]))
    else:
        bb = got[3]
        print("%-7s (%6.2f,%6.2f)  ->  (%6.2f,%6.2f) rot%3d  bbox=(%.2f,%.2f)-(%.2f,%.2f)"
              % (name, before[0], before[1], got[0], got[1], got[2],
                 bb[0], bb[1], bb[2], bb[3]))

if bad:
    print("\nFAILED to place: %s -- nothing written" % ", ".join(bad))
    sys.exit(1)
if DRY:
    print("\n--dry-run: nothing written")
else:
    b.Save(OUT)
    print("\nsaved", OUT)

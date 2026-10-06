"""Silkscreen pass for the 74HC595 strip on the carrier.

DRC reported 14 silk violations, and every one of them is the same mistake:
a text label was left where its symbol's default field offset put it, and
something added later -- the next 595's body outline, a button legend, the
board name -- now runs through it.  Nothing here is electrical; the copper is
untouched.

The strip is too tight to place these by eye (the four 595s are 11.5 mm apart
with 9.48 mm of pad row, so the alley between two of them is 2.01 mm wide),
so this resolves them mechanically: build an index of every F.SilkS graphic,
every F.Cu pad and every other visible silk text, then slide each offender to
the nearest position where its real GetBoundingBox() clears all of it plus a
margin from the board edge.

    python _silkfix.py [--dry-run]
"""
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
S = 1e6
EDGE_M = 0.35          # silk to board outline
PAD_M = 0.06           # silk to exposed copper (silk_over_copper)
SILK_M = 0.06          # silk to silk
CELL = 2.0

DRY = "--dry-run" in sys.argv

b = pcbnew.LoadBoard(BOARD)


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

# ---- the labels we intend to move ------------------------------------
MOVE = {("U3", "Reference"), ("U4", "Reference"), ("U5", "Reference"),
        ("U6", "Reference"), ("C9", "Reference"), ("C10", "Reference"),
        ("C11", "Reference"), ("J8", "Reference"), ("J10", "Reference")}
NAME = "LANFENG-ESP32-S3"

name_uuids = set()
for d in b.GetDrawings():
    if (d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS
            and d.GetText().strip() == NAME):
        name_uuids.add(d.m_Uuid.AsString())

# ---- obstacle index --------------------------------------------------
grid = {}


def add(bb, m):
    e = (bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m)
    for i in range(int(e[0] // CELL), int(e[2] // CELL) + 1):
        for j in range(int(e[1] // CELL), int(e[3] // CELL) + 1):
            grid.setdefault((i, j), []).append(e)


for fp in b.GetFootprints():
    ref = fp.GetReference()
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
    if (d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS
            and d.m_Uuid.AsString() not in name_uuids):
        add(rb(d), SILK_M)
print("obstacles: %d boxes in %d cells" % (sum(len(v) for v in grid.values()), len(grid)))


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


def seek(obj, anchors, angles, span, step, size=None):
    """Nearest legal placement, or None (leaving the object untouched)."""
    home = (obj.GetPosition().x, obj.GetPosition().y, obj.GetTextAngleDegrees())
    if size is not None:
        obj.SetTextSize(pcbnew.VECTOR2I(int(size * S), int(size * S)))
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
# The 595s: straight below the body first (that band is empty from x~52 to the
# right edge), then above it, then the body centre as a last resort.
jobs = []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if (ref, "Reference") not in MOVE:
        continue
    cx = fp.GetPosition().x / S
    if ref.startswith("U"):
        jobs.append((ref, fp.Reference(), [(cx, 72.9), (cx, 65.2), (cx, 68.2)],
                     [0, 90], 5.0, 0.2, None))
    elif ref.startswith("C"):
        jobs.append((ref, fp.Reference(),
                     [(cx + 3.1, 62.9), (cx - 3.4, 62.9), (cx, 59.6), (cx, 65.2)],
                     [0, 90], 3.0, 0.2, None))
    else:                                       # J8 / J10
        y = fp.GetPosition().y / S
        jobs.append((ref, fp.Reference(),
                     [(2.2, y - 4.4), (2.2, y - 6.2), (2.2, y - 8.0), (1.6, y)],
                     [0, 90], 4.0, 0.2, None))

for d in b.GetDrawings():
    if (d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS
            and d.m_Uuid.AsString() in name_uuids):
        jobs.append(("board name", d,
                     [(47.0, 62.7), (77.0, 58.6), (63.0, 72.8), (60.0, 58.4)],
                     [0], 16.0, 0.25, 1.0))

print("\n%-11s %-28s %s" % ("label", "was", "now"))
bad = []
for name, obj, anchors, angles, span, step, size in jobs:
    before = (obj.GetPosition().x / S, obj.GetPosition().y / S)
    got = seek(obj, anchors, angles, span, step, size)
    if got is None:
        bad.append(name)
        print("%-11s (%6.2f,%6.2f)              NO LEGAL SPOT" % (name, before[0], before[1]))
    else:
        bb = got[3]
        print("%-11s (%6.2f,%6.2f)  ->  (%6.2f,%6.2f) rot%3d  bbox=(%.2f,%.2f)-(%.2f,%.2f)%s"
              % (name, before[0], before[1], got[0], got[1], got[2],
                 bb[0], bb[1], bb[2], bb[3], "  size=%.1f" % size if size else ""))

if bad:
    print("\nFAILED to place: %s -- nothing written" % ", ".join(bad))
    sys.exit(1)
if DRY:
    print("\n--dry-run: nothing written")
else:
    b.Save(BOARD)
    print("\nsaved", BOARD)

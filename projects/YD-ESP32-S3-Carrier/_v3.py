"""How +3V3 is chopped up on the board, island by island.

DRC reports +3V3 as the biggest single block of unconnected items, and the
number alone says nothing about the shape of the problem: a net split into two
big islands is one track, a net split into seventeen one-pad fragments is a
distribution scheme.  This groups the net's pads and tracks into islands by
geometric contact and prints each one, so the tie-up can be planned as a spine
plus stubs instead of discovered one DRC line at a time.

  python _v3.py [--net +3V3] [--board PATH]
"""
import importlib.util
import sys

import pcbnew

spec = importlib.util.spec_from_file_location(
    "roc", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
           r"\scripts\route-open-carrier.py")
roc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roc)
S = roc.S

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
NET = "+3V3"
argv = sys.argv[1:]
for k, a in enumerate(argv):
    if a == "--board":
        BOARD = argv[k + 1]
    elif a == "--net":
        NET = argv[k + 1]

TOL = 0.05          # two items this close or closer are the same island

b = pcbnew.LoadBoard(BOARD)
CU = (pcbnew.F_Cu, pcbnew.B_Cu)

items = []          # (label, shape, x, y, layer or None, is_pad)
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() != NET:
            continue
        sh = roc.item_shape(p)
        if sh is None:
            continue
        c = p.GetPosition()
        on = [l for l in CU if p.IsOnLayer(l)]
        both = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        items.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), sh,
                      c.x / S, c.y / S,
                      None if both else (on[0] if on else None), True))
for t in b.GetTracks():
    if t.GetNetname() != NET:
        continue
    sh = roc.item_shape(t)
    if sh is None:
        continue
    c = t.GetPosition()
    if t.GetClass() == "PCB_VIA":
        items.append(("via", sh, c.x / S, c.y / S, None, False))
    else:
        items.append(("trk", sh, c.x / S, c.y / S, t.GetLayer(), False))

n = len(items)
print("net %s on %s: %d item(s)\n" % (NET, BOARD.rsplit("\\", 1)[-1], n))

parent = list(range(n))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def union(i, j):
    ri, rj = find(i), find(j)
    if ri != rj:
        parent[rj] = ri


# Only compare items that share a copper layer (a via or PTH pad is on both).
for i in range(n):
    li = items[i][4]
    for j in range(i + 1, n):
        lj = items[j][4]
        if li is not None and lj is not None and li != lj:
            continue
        if roc.dist_item(items[i][2], items[i][3], items[j][1]) <= TOL:
            union(i, j)
        elif roc.dist_item(items[j][2], items[j][3], items[i][1]) <= TOL:
            union(i, j)

groups = {}
for i in range(n):
    groups.setdefault(find(i), []).append(i)

print("%d island(s):\n" % len(groups))
order = sorted(groups.values(), key=lambda g: -len(g))
for k, g in enumerate(order, 1):
    xs = [items[i][2] for i in g]
    ys = [items[i][3] for i in g]
    pads = [items[i][0] for i in g if items[i][5]]
    trks = sum(1 for i in g if not items[i][5])
    print("island %-2d  %2d item(s)  bbox x %.2f..%.2f  y %.2f..%.2f"
          % (k, len(g), min(xs), max(xs), min(ys), max(ys)))
    if pads:
        print("           pads: %s" % " ".join(sorted(pads)))
    if trks:
        print("           %d track/via item(s)" % trks)

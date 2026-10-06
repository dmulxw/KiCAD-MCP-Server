"""Are the four decoupling caps what reduce the west strip to one lane?

_tp_westband.py found that of the 0.90 mm of legal track centre west of the 595
pad column (x 90.55..91.45), only x 90.55..90.75 is free for the whole 70 mm
register span -- one lane, where four nets (IO10 SRCLK, IO11 RCLK, IO12 /OE,
+3V3) need to run.

The placement dump shows 4 capacitors at x 91.06..92.94, y 180.01..240.99.  Their
west pad edge at 91.06 would push the easternmost legal track centre to
91.06-0.2-0.1 = 90.76, which is exactly the observed wall.  If that is right,
the single lane is not a property of the board -- it is four parts sitting in
the corridor, and moving them is a placement fix, not a layer change.

This measures: the caps' exact pad geometry, and the free width of the west
strip band by band (register bodies vs the gaps between them) so it is clear
whether the corridor is blocked everywhere or only where the caps are.

  python _tp_caps.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
EDGE = 89.95
EDGE_CLR = 0.5
CLR = 0.2

board = pcbnew.LoadBoard(BOARD)

# ---- the capacitors --------------------------------------------------------
print("=== capacitors, pad by pad ===")
caps = [fp for fp in board.GetFootprints()
        if str(fp.GetReference()).startswith("C")]
for fp in sorted(caps, key=lambda f: f.GetPosition().y):
    q = fp.GetBoundingBox(False, False)
    print("  %-4s %-8s at (%.2f, %.2f)  bbox x %.3f..%.3f y %.3f..%.3f"
          % (str(fp.GetReference()), str(fp.GetValue()),
             TO(fp.GetPosition().x), TO(fp.GetPosition().y),
             q.GetLeft() / S, q.GetRight() / S,
             q.GetTop() / S, q.GetBottom() / S))
    for p in fp.Pads():
        r = p.GetBoundingBox()
        print("      pad %-3s %-8s  x %.3f..%.3f  y %.3f..%.3f"
              % (str(p.GetNumber()), str(p.GetNetname()),
                 r.GetLeft() / S, r.GetRight() / S,
                 r.GetTop() / S, r.GetBottom() / S))

# ---- everything that intrudes on the west strip ---------------------------
XLO = EDGE + EDGE_CLR + 0.1     # 90.55  westernmost legal centre
print("\n=== what reaches into the west strip (x < 92.0) below the header ===")
Y0, Y1 = 166.0, 245.0
occ = defaultdict(list)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        x, y = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        if x - r < 92.0 and Y0 <= y <= Y1:
            occ["VIA:" + str(t.GetNetname())].append((y, x - r))
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    if min(x1, x2) - w < 92.0 and max(y1, y2) >= Y0 and min(y1, y2) <= Y1:
        lay = "F" if t.GetLayer() == pcbnew.F_Cu else (
              "B" if t.GetLayer() == pcbnew.B_Cu else "?")
        occ[lay + ":" + str(t.GetNetname())].append(
            (min(y1, y2), min(x1, x2) - w))
for k in sorted(occ):
    ys = [y for y, _x in occ[k]]
    xw = min(x for _y, x in occ[k])
    print("  %-16s %3d  y %6.1f..%-6.1f  westmost copper x %.3f"
          % (k, len(occ[k]), min(ys), max(ys), xw))

# ---- free width of the strip, band by band ---------------------------------
# obstacle x-extents per band, from every track/via/pad that crosses it
obst = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        x, y = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        obst.append((x - r, x + r, y - r, y + r, "V", str(t.GetNetname())))
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    lay = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B"}.get(t.GetLayer())
    if not lay:
        continue
    obst.append((min(x1, x2) - w, max(x1, x2) + w,
                 min(y1, y2) - w, max(y1, y2) + w, lay, str(t.GetNetname())))
for fp in board.GetFootprints():
    for p in fp.Pads():
        r = p.GetBoundingBox()
        obst.append((r.GetLeft() / S, r.GetRight() / S,
                     r.GetTop() / S, r.GetBottom() / S,
                     "P", str(fp.GetReference())))

BANDS = [("U1 body", 168.56, 177.44), ("  gap 1", 177.44, 188.56),
         ("U2 body", 188.56, 197.44), ("  gap 2", 197.44, 208.56),
         ("U3 body", 208.56, 217.44), ("  gap 3", 217.44, 228.56),
         ("U4 body", 228.56, 237.44), ("  below", 237.44, 245.0)]
print("\n=== west strip occupancy, band by band (x 90.45..91.90) ===")
print("  %-10s %-16s %s" % ("band", "y", "who reaches in (westmost copper x)"))
for (name, y0, y1) in BANDS:
    hits = defaultdict(lambda: 1e9)
    for (l, r, t0, b, tag, net) in obst:
        if b < y0 or t0 > y1:
            continue
        if l > 91.90:
            continue
        if tag in ("F", "B", "V"):
            hits[tag + ":" + net] = min(hits[tag + ":" + net], l)
    s = "  ".join("%s@%.2f" % (k, v) for k, v in sorted(hits.items())
                  if v < 92.0)
    print("  %-10s %6.1f..%-6.1f %s" % (name, y0, y1, s or "CLEAR"))

# ---- how many 0.2 lanes fit, given the caps' west edge ---------------------
print("\n=== lane capacity of x 90.55..91.90 ===")
for wall, why in ((91.06, "caps' west pad edge (current)"),
                  (91.75, "595 pad column west edge (if caps move clear)")):
    hi = wall - CLR - 0.1
    c = []
    x = XLO
    while x <= hi + 1e-9:
        c.append(round(x, 3))
        x += 0.4
    print("  wall %.2f (%s): legal centres %.2f..%.2f -> %d lane(s) %s"
          % (wall, why, XLO, hi, len(c), c))

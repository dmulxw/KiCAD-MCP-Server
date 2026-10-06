"""Where everything sits on the panel, and how full the board actually is.

Three independent measurements now say the same thing -- the R column has no
B.Cu replacement lane, the 595 control bus needs four full-span verticals and
gets one clean 0.2 channel, and Freerouting's fanout escapes only 58% of SMD
pins.  Before concluding that two layers is simply not enough, check the one
lever that is free and that the user actually asked for: the 595s were supposed
to sit *near the pin header*, and if they drifted away from it, that is a
placement fix rather than a routing fix.

Prints the board outline, every footprint grouped by prefix, the connectors in
full, and a coarse copper-density grid over the whole board so empty regions
are visible.

  python _tp_place2.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6

board = pcbnew.LoadBoard(BOARD)

# ---- board outline ---------------------------------------------------------
xs, ys = [], []
for d in board.GetDrawings():
    if d.GetLayer() != pcbnew.Edge_Cuts:
        continue
    r = d.GetBoundingBox()
    xs += [r.GetLeft() / S, r.GetRight() / S]
    ys += [r.GetTop() / S, r.GetBottom() / S]
X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
print("board outline  x %.2f..%.2f  (%.1f mm)   y %.2f..%.2f  (%.1f mm)"
      % (X0, X1, X1 - X0, Y0, Y1, Y1 - Y0))

# ---- footprints ------------------------------------------------------------
rows = []
for fp in board.GetFootprints():
    q = fp.GetBoundingBox(False, False)
    rows.append((str(fp.GetReference()),
                 (q.GetLeft() / S, q.GetTop() / S,
                  q.GetRight() / S, q.GetBottom() / S),
                 str(fp.GetValue())))

pref = defaultdict(list)
for (ref, bb, val) in rows:
    pref[ref.rstrip("0123456789")].append((ref, bb, val))

print("\n=== %d footprint(s), by prefix ===" % len(rows))
for p, lst in sorted(pref.items(), key=lambda kv: -len(kv[1])):
    xlo = min(b[0] for _r, b, _v in lst)
    xhi = max(b[2] for _r, b, _v in lst)
    ylo = min(b[1] for _r, b, _v in lst)
    yhi = max(b[3] for _r, b, _v in lst)
    print("  %-5s %3d  x %7.2f..%-7.2f y %7.2f..%-7.2f  e.g. %s"
          % (p, len(lst), xlo, xhi, ylo, yhi, lst[0][2][:24]))

# ---- connectors and ICs in full --------------------------------------------
print("\n=== connectors / ICs / switches ===")
for (ref, bb, val) in sorted(rows):
    if ref[0] in ("J", "P", "SW", "U", "Y", "X", "F"):
        print("  %-6s %-30s x %7.2f..%-7.2f y %7.2f..%-7.2f"
              % (ref, val[:30], bb[0], bb[2], bb[1], bb[3]))

# ---- coarse copper density -------------------------------------------------
GW = 5.0
nx = int((X1 - X0) / GW) + 1
ny = int((Y1 - Y0) / GW) + 1
cu = defaultdict(int)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        cu[(int((TO(q.x) - X0) / GW), int((TO(q.y) - Y0) / GW))] += 1
        continue
    s, e = t.GetStart(), t.GetEnd()
    sx, sy, ex, ey = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    n = max(1, int(max(abs(ex - sx), abs(ey - sy)) / (GW / 3)))
    for k in range(n + 1):
        x = sx + (ex - sx) * k / n
        y = sy + (ey - sy) * k / n
        cu[(int((x - X0) / GW), int((y - Y0) / GW))] += 1

print("\n=== copper items per %.0f mm cell  ('.' = empty, '#' = >=60) ===" % GW)
hdr = "        "
for c in range(nx):
    hdr += "%4d" % (X0 + c * GW) if c % 4 == 0 else "    "
print(hdr)
for r in range(ny):
    line = ""
    for c in range(nx):
        n = cu[(c, r)]
        line += "   ." if n == 0 else ("   #" if n >= 60 else "%4d" % n)
    print("y%6.0f %s" % (Y0 + r * GW, line))

# ---- how many cells are empty, by column band ------------------------------
print("\n=== empty cells per 10 mm x-band (out of %d rows) ===" % ny)
for b0 in range(0, nx, 2):
    empty = sum(1 for r in range(ny)
                for c in (b0, b0 + 1)
                if c < nx and cu[(c, r)] == 0)
    cells = sum(1 for c in (b0, b0 + 1) if c < nx) * ny
    print("  x %6.0f..%-6.0f  %2d/%2d empty"
          % (X0 + b0 * GW, X0 + (b0 + 1) * GW + GW, empty, cells))

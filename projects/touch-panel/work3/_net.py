"""Dump one net's copper: every item, its true endpoints, layer, sorted.

_near.py answers "what is around this point".  This answers "what IS this net"
-- the shape of the fragmentation, which is the only thing that explains why
two fragments 4mm apart cost a 146mm bridge.  A wall of another net between
them is invisible in a per-net view and obvious in a board view; the reverse is
true here, so both tools earn their place.

    python _net.py <board> <net> [x0 y0 x1 y1]
"""
import sys

sys.path.insert(0, __import__("os").getcwd())
import pcbnew                                                        # noqa: E402

S = 1e6
board = pcbnew.LoadBoard(sys.argv[1])
net = sys.argv[2]
box = [float(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else None

rows = []
for t in board.GetTracks():
    if t.GetNetname() != net:
        continue
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = s.x / S, s.y / S, e.x / S, e.y / S
    if box and not (ax <= box[2] and bx >= box[0] and ay <= box[3] and by >= box[1]):
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        kind, L = "VIA", "THRU"
    else:
        kind, L = "TRK", "/".join(n for n, c in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu))
                                  if t.IsOnLayer(c))
    rows.append((min(ay, by), min(ax, bx), kind, L, ax, ay, bx, by))

for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() != net:
            continue
        c = p.GetPosition()
        cx, cy = c.x / S, c.y / S
        if box and not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
            continue
        L = "/".join(n for n, l in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu))
                     if p.IsOnLayer(l))
        rows.append((cy, cx, "PAD " + f.GetReference() + "." + p.GetNumber(), L,
                     cx, cy, cx, cy))

rows.sort()
print("%s: %d item(s) on net %s" % (sys.argv[1], len(rows), net))
for _, _, kind, L, ax, ay, bx, by in rows:
    if kind.startswith("VIA"):
        print("  %-14s %-4s (%8.3f,%8.3f)" % (kind, L, ax, ay))
    elif kind.startswith("PAD"):
        print("  %-14s %-4s (%8.3f,%8.3f)" % (kind, L, ax, ay))
    else:
        ln = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        print("  %-14s %-4s (%8.3f,%8.3f)->(%8.3f,%8.3f)  %6.3fmm"
              % (kind, L, ax, ay, bx, by, ln))

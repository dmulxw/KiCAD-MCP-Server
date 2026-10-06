"""Where, if anywhere, can an F.Cu trace cross the band x=100.2..101.9 ?

The B.Cu side of that band is three parallel row/column trunks and is solid for
the whole southern half of the board.  So the only way from the 595 column to
the R pads is on F.Cu, and the only thing stopping that is whatever F.Cu copper
crosses the band.  List those, subtract their footprints from the band, and the
remaining y gaps are the doors.
"""
import pcbnew
BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X1, X2 = 100.02, 101.98      # band to cross
CLEAR, HW = 0.16, 0.10       # our trace: 0.20 wide
board = pcbnew.LoadBoard(BOARD)

crossers = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    w = TO(t.GetWidth())
    if max(ax, bx) + w/2 < X1 or min(ax, bx) - w/2 > X2:
        continue
    crossers.append((t.GetNetname(), ax, ay, bx, by, w))
print("F.Cu copper intersecting the band x %.2f..%.2f : %d piece(s)"
      % (X1, X2, len(crossers)))
for (n, ax, ay, bx, by, w) in sorted(crossers, key=lambda e: min(e[2], e[4])):
    print("   %-9s (%.3f,%.3f)->(%.3f,%.3f) w=%.2f  y %.2f..%.2f"
          % (n, ax, ay, bx, by, w, min(ay, by)-w/2, max(ay, by)+w/2))

# y spans of the band that any crosser's clearance blocks
blocked_spans = sorted((min(ay, by) - w/2 - CLEAR - HW,
                        max(ay, by) + w/2 + CLEAR + HW)
                       for (_n, ax, ay, bx, by, w) in crossers)
merged = []
for (s, e) in blocked_spans:
    if merged and s <= merged[-1][1]:
        merged[-1][1] = max(merged[-1][1], e)
    else:
        merged.append([s, e])
print("\nband is trace-blocked over these y spans:")
for (s, e) in merged:
    print("   y %7.2f .. %7.2f   (%.2f mm)" % (s, e, e - s))
print("\n=> DOORS (gaps in the band, inside the board's y 100..250):")
prev = 100.0
for (s, e) in merged:
    if s - prev > 0.62:            # 0.20 trace + 2 x clearance fits
        print("   y %7.2f .. %7.2f   gap %.2f mm" % (prev, s, s - prev))
    prev = max(prev, e)
if 250.0 - prev > 0.62:
    print("   y %7.2f .. %7.2f   gap %.2f mm" % (prev, 250.0, 250.0 - prev))

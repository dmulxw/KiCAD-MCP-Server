"""Lift the three B.Cu verticals that seal the west wall, plus their feeders.

SMD pads are F.Cu-only, so neither the 595 columns nor the R-pad column obstruct
B.Cu -- the bottom layer is held shut by three nets laying one long 0.20 track
each down x=100.648 / 101.050 / 101.452.  Everything else on B.Cu in that band is
crossable, and the F.Cu GND serpentine lives at the same x, which is why there is
no layer to duck under today.

Lifting the trunks opens x 100.29..101.81 on B.Cu.  A stranded net can then cross
under the GND spine: F.Cu east to a via, B.Cu beneath the spine, via back up on
the far side.  GND's own mesh is never touched.

The feeders have to go with the trunks.  CSEL4 reaches its trunk through a second
vertical at x=100.550 (which is inside the band too) fed by a diagonal from J1A
pad 14; ROW1 and ROW8 arrive at their trunk tops through short connectors from
the vias that hang off R2 pad 1 and R9 pad 1.  Anything left behind would keep
blocking the band and would straddle the trunk's new lane.  The vias themselves
stay -- they are the attachment points the router will reconnect to.

The pieces below y=242 stay: they carry each net east past the last row, and they
give the re-routed trunks something to land on.

  python _tp_openband.py [out.kicad_pcb]        # default: in place
"""
import sys
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
TOL = 0.005

# net, layer, x1, y1, x2, y2 -- endpoint order is not significant
DOOM = [
    ("CSEL4", "B", 100.648, 112.949, 100.648, 242.039),
    ("CSEL4", "B", 100.550, 119.050, 100.550, 143.450),
    ("CSEL4", "B",  95.450, 148.550, 100.550, 143.450),
    ("CSEL4", "B", 100.650, 119.050, 100.648, 119.050),
    ("CSEL4", "B", 100.550, 119.050, 100.650, 119.050),
    ("ROW1",  "B", 101.050, 119.316, 101.050, 241.553),
    ("ROW1",  "B", 101.628, 118.738, 101.050, 119.316),
    ("ROW8",  "B", 101.452, 164.778, 101.452, 239.292),
    ("ROW8",  "B", 102.842, 163.388, 101.452, 164.778),
]

out = sys.argv[1] if len(sys.argv) > 1 else BOARD
board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)

LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}


def same(a, b):
    return abs(a - b) <= TOL


def matches(t, spec):
    net, lay, x1, y1, x2, y2 = spec
    if t.GetNetname() != net:
        return False
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != LAYER[lay]:
        return False
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    fwd = same(ax, x1) and same(ay, y1) and same(bx, x2) and same(by, y2)
    rev = same(ax, x2) and same(ay, y2) and same(bx, x1) and same(by, y1)
    return fwd or rev


_keep_alive = []
hit = [False] * len(DOOM)
for t in list(board.GetTracks()):
    for i, spec in enumerate(DOOM):
        if hit[i] or not matches(t, spec):
            continue
        board.Remove(t)
        _keep_alive.append(t)          # see clear_routing(): must outlive the save
        hit[i] = True
        break

missing = [DOOM[i] for i, h in enumerate(hit) if not h]
print("removed %d of %d segment(s)" % (sum(hit), len(DOOM)))
for spec in missing:
    print("   NOT FOUND: %s %s (%s,%s)->(%s,%s)" % spec)

# What is left on B.Cu in the band -- this is the number that has to come out near
# zero, and the whole point of the exercise.
print("\nB.Cu copper still reaching into the band x 100.2..101.9, y 110..242:")
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.B_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth())
    if max(x1, x2) + w / 2 < 100.2 or min(x1, x2) - w / 2 > 101.9:
        continue
    if max(y1, y2) < 110.0 or min(y1, y2) > 242.0:
        continue
    print("   %-9s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f"
          % (t.GetNetname(), x1, y1, x2, y2, w))
print("   vias:")
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    p = t.GetPosition()
    x, y = TO(p.x), TO(p.y)
    if 100.2 <= x <= 101.9 and 110.0 <= y <= 242.0:
        print("   %-9s (%8.3f,%8.3f)" % (t.GetNetname(), x, y))

board.Save(out)
print("\nsaved", out)

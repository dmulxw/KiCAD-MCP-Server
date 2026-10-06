"""Two questions at once: what do the panel connectors actually carry, and
where is there a hole big enough for a SOIC-16 + its caps?

The 595s were dropped into the left corridor, which turns out to be J1A's own
vertical bus channel.  Before moving them anywhere I want the connectors'
pinout and a coarse picture of free copper space, so the new site is chosen
from measurement rather than from the first gap that looks empty.
"""
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

# --- 1. the connectors, pin by pin -----------------------------------------
print("=" * 78)
print("connector pinouts")
print("=" * 78)
for ref in ("J1A", "J1B", "J1"):
    fp = fp_ = board.FindFootprintByReference(ref)
    if fp is None:
        print("%s: not found" % ref)
        continue
    p = fp.GetPosition()
    pads = sorted(fp.Pads(), key=lambda q: int(q.GetNumber()))
    nets = []
    for q in pads:
        n = q.GetNetname()
        nets.append(n)
    uniq = sorted({n for n in nets if n})
    print("\n%s at (%7.3f,%7.3f) rot=%g  %d pads, %d net(s)"
          % (ref, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
             fp.GetOrientationDegrees(), len(pads), len(uniq)))
    print("   %s" % ", ".join(uniq))
    for q in pads:
        pos = q.GetPosition()
        print("     pad %-3s (%8.3f,%8.3f) %-8s %s"
              % (q.GetNumber(), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                 q.GetLayer() == 0 and "F.Cu" or "B.Cu", q.GetNetname() or "-"))

# --- 2. coarse free-space map ----------------------------------------------
blocked, vb = rt.blocked_for("__no_such_net__", R.DEFAULT_W / 2.0)
free = (~blocked) & (~rt.edge)
print("\n" + "=" * 78)
print("free space, both layers   ('.'=F+B free  'f'=F only  'b'=B only  '#'=blocked)")
print("=" * 78)

SX, SY = 6, 12                     # 1.2 mm x 2.4 mm per character
nx, ny = R.NX // SX, R.NY // SY
grid = [[" "] * nx for _ in range(ny)]
for J in range(ny):
    j0, j1 = J * SY, (J + 1) * SY
    for I in range(nx):
        i0, i1 = I * SX, (I + 1) * SX
        f = free[0, i0:i1, j0:j1].any()
        b = free[1, i0:i1, j0:j1].any()
        grid[J][I] = "." if (f and b) else ("f" if f else ("b" if b else "#"))

marks = {}
for ref in ("U1", "U2", "U3", "U4"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        continue
    p = fp.GetPosition()
    marks[(R.gi(pcbnew.ToMM(p.x)) // SX, R.gj(pcbnew.ToMM(p.y)) // SY)] = ref[1]
for ref in ("J1A", "J1B", "J1"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        continue
    p = fp.GetPosition()
    x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
    marks[(R.gi(x) // SX, R.gj(y) // SY)] = {"J1A": "A", "J1B": "B", "J1": "1"}[ref]
for (I, J), c in marks.items():
    if 0 <= J < ny and 0 <= I < nx:
        grid[J][I] = c

hdr = "      " + "".join(str((i * SX * int(R.GRID * 1000) // 100) // 100 % 10)
                         for i in range(nx))
print(hdr)
print("      " + "".join("|" if i % 5 == 0 else " " for i in range(nx)))
for J in range(ny):
    y = R.my(J * SY)
    print("%6.1f%s" % (y, "".join(grid[J])))

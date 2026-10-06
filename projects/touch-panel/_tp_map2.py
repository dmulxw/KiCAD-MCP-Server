"""Coarse free-space map + the landmarks that constrain a new 595 site."""
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

blocked, vb = rt.blocked_for("__no_such_net__", R.DEFAULT_W / 2.0)
free = (~blocked) & (~rt.edge)

SX, SY = 6, 12
nx, ny = R.NX // SX, R.NY // SY
grid = [[" "] * nx for _ in range(ny)]
for J in range(ny):
    for I in range(nx):
        f = free[0, I * SX:(I + 1) * SX, J * SY:(J + 1) * SY].any()
        b = free[1, I * SX:(I + 1) * SX, J * SY:(J + 1) * SY].any()
        grid[J][I] = "." if (f and b) else ("f" if f else ("b" if b else "#"))

marks = {}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    ch = None
    if ref in ("U1", "U2", "U3", "U4"):
        ch = ref[1]
    elif ref in ("J1A", "J1B", "J1"):
        ch = {"J1A": "A", "J1B": "B", "J1": "1"}[ref]
    elif ref.startswith("R") and ref[1:].isdigit() and 1 <= int(ref[1:]) <= 21:
        ch = "r"                       # the row-resistor column
    if ch is None:
        continue
    p = fp.GetPosition()
    I = R.gi(pcbnew.ToMM(p.x)) // SX
    J = R.gj(pcbnew.ToMM(p.y)) // SY
    if 0 <= J < ny and 0 <= I < nx:
        marks.setdefault((I, J), []).append(ch)
for (I, J), cs in marks.items():
    grid[J][I] = cs[0] if len(cs) == 1 else "*"

print("free space: '.'=F+B  'f'=F only  'b'=B only  '#'=blocked")
print("marks: 1..4=U1..U4   A=J1A   B=J1B   1=J1   r=row-resistor column")
print("x runs %.2f .. %.2f mm (1 char = %.1f mm);  y runs %.2f .. %.2f mm (1 char = %.1f mm)"
      % (R.mx(0), R.mx(R.NX - 1), SX * R.GRID,
         R.my(0), R.my(R.NY - 1), SY * R.GRID))
print()
print("       " + "".join("%d" % ((I * SX // 50) % 10) for I in range(nx)))
for J in range(ny):
    print("%6.1f %s" % (R.my(J * SY), "".join(grid[J])))

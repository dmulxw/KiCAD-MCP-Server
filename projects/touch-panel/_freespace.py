"""Where is the panel schematic actually empty.

The 595s have to land on a sheet that already holds 974 labels, 262 symbols and
220 transistors, and "x 200..395 looks empty" is the kind of claim that costs a
morning when it turns out a wire run lives there.  This bucketises every
element anchor in the sheet and prints the occupancy as a coarse map, so a
landing zone is chosen from the file rather than from the neighbourhood.

  python _freespace.py [--sch PATH] [--x0 150] [--x1 420] [--y0 10] [--y1 380]
"""
import collections
import re
import sys

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_sch")
X0, X1, Y0, Y1 = 150.0, 420.0, 10.0, 380.0
CELL = 20.0

argv = sys.argv[1:]
k = 0
while k < len(argv):
    a = argv[k]
    if a == "--sch":
        SCH = argv[k + 1]
    elif a == "--x0":
        X0 = float(argv[k + 1])
    elif a == "--x1":
        X1 = float(argv[k + 1])
    elif a == "--y0":
        Y0 = float(argv[k + 1])
    elif a == "--y1":
        Y1 = float(argv[k + 1])
    else:
        sys.exit("unknown %s" % a)
    k += 2

txt = open(SCH, encoding="utf-8").read()

# Depth-3 anchors are the (at ...) of a top-level item's own geometry.  A
# symbol instance's origin sits at depth 3 too, which is the point we want: it
# is the centre of the body, so a cell holding a symbol is not free space.
cells = collections.Counter()
for m in re.finditer(r"^\t\t\t\(at ([\d.-]+) ([\d.-]+)", txt, re.M):
    x, y = float(m.group(1)), float(m.group(2))
    if X0 <= x <= X1 and Y0 <= y <= Y1:
        cells[(int((x - X0) // CELL), int((y - Y0) // CELL))] += 1

nx = int((X1 - X0) // CELL) + 1
print("%s" % SCH.rsplit("\\", 1)[-1])
print("window x %.0f..%.0f  y %.0f..%.0f  cell %.0f mm  %d anchor(s)\n"
      % (X0, X1, Y0, Y1, CELL, sum(cells.values())))

print("     " + "".join("%5.0f" % (X0 + i * CELL) for i in range(nx)))
for j in range(int((Y1 - Y0) // CELL) + 1):
    row = "%4.0f " % (Y0 + j * CELL)
    for i in range(nx):
        n = cells.get((i, j), 0)
        row += "%5s" % ("." if n == 0 else n)
    print(row)

# The biggest all-empty run of cells is the only number worth quoting.
best, cur = None, 0
for j in range(int((Y1 - Y0) // CELL) + 1):
    for i in range(nx):
        cur = 0 if cells.get((i, j), 0) else cur + 1
        if best is None or cur > best[0]:
            best = (cur, i, j)
print("\nlongest empty horizontal run: %d cell(s), ending at "
      "(%.0f, %.0f)" % (best[0], X0 + best[1] * CELL, Y0 + best[2] * CELL))

"""ASCII map of the router's own legality field.

Imports route-open-carrier.py and asks its Grid the same questions the A* asks,
so what is printed here is exactly what the search sees -- not an approximation.

  python _map.py X0 X1 Y0 Y1 [--layer F|B|vias] [--step 0.1] [--board PATH]

'#' = neither layer can carry a track, '.' = at least one can, '+' = a via fits.
"""
import importlib.util
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
for _k, _a in enumerate(sys.argv):
    if _a == "--board":
        BOARD = sys.argv[_k + 1]

spec = importlib.util.spec_from_file_location(
    "roc", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
           r"\scripts\route-open-carrier.py")
roc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roc)

x0, x1, y0, y1 = (float(a) for a in sys.argv[1:5])
step = 0.1
layer_sel = "both"
for k, a in enumerate(sys.argv):
    if a == "--step":
        step = float(sys.argv[k + 1])
    if a == "--layer":
        layer_sel = sys.argv[k + 1]

b = pcbnew.LoadBoard(BOARD)
keep = 0.16 + roc.TRACK_W / 2 + 0.08
pad_keep = 0.16 + roc.VIA_DIA / 2 + 0.08
edge_keep = 0.5 + 0.15 + 0.08
g = roc.Grid(b, step, keep, edge_keep, pad_keep, edge_keep)

items = list(b.GetTracks())
for fp in b.GetFootprints():
    items.extend(fp.Pads())
print("stamping %d item(s), step %.3f  keep track=%.2f via=%.2f" %
      (len(items), step, keep, pad_keep))
g.build([pcbnew.F_Cu, pcbnew.B_Cu], items)

nx = int(round((x1 - x0) / step))
ny = int(round((y1 - y0) / step))
if nx * ny > 200000:
    print("region too large: %d cells -- raise --step or shrink the box" % (nx * ny))
    sys.exit(1)

layers = {"F": [pcbnew.F_Cu], "B": [pcbnew.B_Cu],
          "both": [pcbnew.F_Cu, pcbnew.B_Cu]}[layer_sel]
print("legend: layer letter = only that layer legal, '*' = both, "
      "'+' = via ok, '#' = blocked, ' ' = outside")
free = 0
for j in range(ny + 1):
    row = []
    for i in range(nx + 1):
        x, y = x0 + i * step, y0 + j * step
        gi, gj = g.ij(x, y)
        okf = g.track_ok(pcbnew.F_Cu, gi, gj)
        okb = g.track_ok(pcbnew.B_Cu, gi, gj)
        vok = g.via_ok(gi, gj)
        if not (okf or okb):
            row.append("#")
        elif vok:
            row.append("+")
        elif okf and okb:
            row.append("*")
        elif okf:
            row.append("F")
        else:
            row.append("B")
        if okf or okb:
            free += 1
    print("%6.2f %s" % (y0 + j * step, "".join(row)))
print("free cells: %d / %d = %.1f%%" % (free, (nx + 1) * (ny + 1),
                                        100.0 * free / ((nx + 1) * (ny + 1))))
print("x axis runs %.2f -> %.2f, one char per %.2f mm" % (x0, x1, step))

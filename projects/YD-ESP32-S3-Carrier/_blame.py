"""Name the copper responsible for a blocked cell.

_map.py says where the router cannot go; this says why.  Hand it a box and it
lists every copper item in the box grouped by net and layer, with the shape and
extent that matters, so a sealed corridor turns into a list of names.

  python _blame.py X0 X1 Y0 Y1 [--board PATH] [--safety S]
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
SAFETY = 0.03
argv = sys.argv[1:]
X0, X1, Y0, Y1 = (float(a) for a in argv[:4])
for k, a in enumerate(argv):
    if a == "--board":
        BOARD = argv[k + 1]
    elif a == "--safety":
        SAFETY = float(argv[k + 1])

b = pcbnew.LoadBoard(BOARD)
keep = 0.16 + roc.TRACK_W / 2 + SAFETY

rows = []


def note(kind, net, lay, sh, extra=""):
    if sh is None:
        return
    x0, y0, x1, y1, r, box = sh
    if x1 < X0 or x0 > X1 or y1 < Y0 or y0 > Y1:
        return
    rows.append((kind, net, lay, x0, y0, x1, y1, extra))


for t in b.GetTracks():
    sh = roc.item_shape(t)
    if t.GetClass() == "PCB_VIA":
        note("VIA", t.GetNetname(), "all", sh)
    else:
        lay = b.GetLayerName(t.GetLayer())
        s, e = t.GetStart(), t.GetEnd()
        note("TRK", t.GetNetname(), lay, sh,
             "(%.2f,%.2f)->(%.2f,%.2f) w%.2f"
             % (s.x / S, s.y / S, e.x / S, e.y / S, t.GetWidth() / S))
for fp in b.GetFootprints():
    for p in fp.Pads():
        sh = roc.item_shape(p)
        bb = p.GetBoundingBox()
        note("PAD", p.GetNetname(), "PTH" if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
             else b.GetLayerName(p.GetLayer()), sh,
             "%s.%s %.2fx%.2f" % (fp.GetReference(), p.GetNumber(),
                                  bb.GetWidth() / S, bb.GetHeight() / S))

print("board %s   box x %.2f..%.2f  y %.2f..%.2f   track keep %.3f"
      % (BOARD.rsplit("\\", 1)[-1], X0, X1, Y0, Y1, keep))
print("%d item(s) in the box\n" % len(rows))

bynet = {}
for r in rows:
    bynet.setdefault(r[1], []).append(r)
for net in sorted(bynet, key=lambda n: (n == "GND", n)):
    grp = bynet[net]
    print("%-16s %d item(s)" % (net, len(grp)))
    for kind, _n, lay, x0, y0, x1, y1, extra in sorted(grp, key=lambda r: r[5]):
        print("    %-4s %-4s x %7.2f..%7.2f  y %7.2f..%7.2f  %s"
              % (kind, lay, x0, x1, y0, y1, extra))

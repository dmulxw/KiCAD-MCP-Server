import importlib.util, pcbnew
spec = importlib.util.spec_from_file_location("roc", "scripts/route-open-carrier.py")
roc = importlib.util.module_from_spec(spec); spec.loader.exec_module(roc)
S = 1e6
board = pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb")
name = "ROW1"
own = roc.net_items(board, name)
others = [it for it in board.GetTracks() if it.GetNetname() != name]
for fp in board.GetFootprints():
    others.extend(p for p in fp.Pads() if p.GetNetname() != name)
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
keep = 0.16 + 0.3/2 + 0.08
pad_keep = 0.16 + 0.6/2 + 0.08
g = roc.Grid(board, 0.1, keep, 0.16+0.15+0.08, pad_keep, 0.16+0.3+0.08)
g.build(layers, others)
print("keep=%.3f pad_keep=%.3f  F_Cu=%s B_Cu=%s" % (keep, pad_keep, pcbnew.F_Cu, pcbnew.B_Cu))

def sym(layer, i, j):
    gap, who = g.cell(layer, i, j)
    if gap < 0: return "#"          # inside other-net copper
    if gap < keep: return "x"       # too close for a track
    if g.via_ok(i, j): return "*"   # track + via legal
    return "."

print("\nF.Cu   x=50.0..56.4,  y=67.0..73.0   (# inside, x too close, * via-ok, . free)")
xs = [50.0 + k*0.1 for k in range(65)]
ys = [67.0 + k*0.1 for k in range(61)]
print("        " + "".join(str(int(round((x*10) % 100/10))) for x in xs))
for y in ys:
    j = g.ij(xs[0], y)[1]
    row = "".join(sym(pcbnew.F_Cu, g.ij(x, y)[0], j) for x in xs)
    mark = " <-- pad row" if abs(y-70.675) < 0.05 else ""
    print("y=%6.2f %s%s" % (y, row, mark))

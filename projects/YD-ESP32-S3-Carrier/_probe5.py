import math
import pcbnew

b = pcbnew.LoadBoard("_base595.kicad_pcb")

# pad index: (x, y, net, ref.pad)
pads = []
for fp in b.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        pads.append((c.x / 1e6, c.y / 1e6, p.GetNetname(), "%s.%s" % (fp.GetReference(), p.GetNumber())))

def nearest_foreign(x, y, net, k=6):
    out = []
    for (px, py, pn, name) in pads:
        if pn == net:
            continue
        out.append((math.hypot(px - x, py - y), pn, name))
    out.sort()
    return out[:k]

NETS = ["ROW1", "ROW4", "ROW10", "ROW18", "ROW19", "ROW20", "CSEL0", "CSEL4", "CSEL5"]
for net in NETS:
    mine = [p for p in pads if p[2] == net]
    print("=== %s : %d pad(s)" % (net, len(mine)))
    for (x, y, _n, name) in mine:
        print("   pad %-8s at (%.2f, %.2f)" % (name, x, y))
        for (d, pn, other) in nearest_foreign(x, y, net, 4):
            print("        %.3f mm -> %-8s %s" % (d, other, pn))

"""Dump the raw occupancy bits for a window, so the layer filter can be trusted.

  python _tp_raw.py X0 Y0 X1 Y1

Prints, per cell, the hex-ish tuple of which sources marked it:
    t=tracks  p=pads  f=footprints  e=edge   and the copper layers seen.
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

WX0, WY0, WX1, WY1 = (float(v) for v in sys.argv[1:5])

b = pcbnew.LoadBoard(PCB)
NX = int(WX1 - WX0)
NY = int(WY1 - WY0)


def rect(o):
    r = o.GetBoundingBox()
    return (pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY()),
            pcbnew.ToMM(r.GetX() + r.GetWidth()),
            pcbnew.ToMM(r.GetY() + r.GetHeight()))


tk = [[set() for _ in range(NX)] for _ in range(NY)]
pd = [[set() for _ in range(NX)] for _ in range(NY)]
fp_ = [[False] * NX for _ in range(NY)]


def mark(g, o, val):
    ax0, ay0, ax1, ay1 = rect(o)
    ix0 = max(0, int(ax0 - WX0))
    ix1 = min(NX - 1, int(ax1 - WX0))
    iy0 = max(0, int(ay0 - WY0))
    iy1 = min(NY - 1, int(ay1 - WY0))
    for iy in range(iy0, iy1 + 1):
        for ix in range(ix0, ix1 + 1):
            if val is None:
                fp_[iy][ix] = True
            else:
                g[iy][ix].add(val)


n_tr = n_pad = 0
for fp in b.GetFootprints():
    mark(fp_, fp, None)
    for p in fp.Pads():
        ls = p.GetLayerSet()
        n_pad += 1
        mark(pd, p, (p.GetNumber(),
                     ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                     fp.GetReference()))
for t in b.GetTracks():
    n_tr += 1
    mark(tk, t, b.GetLayerName(t.GetLayer()))

print("footprints %d  pads %d  tracks/vias %d"
      % (len(list(b.GetFootprints())), n_pad, n_tr))
print("window x %.0f..%.0f y %.0f..%.0f" % (WX0, WX1, WY0, WY1))


def cell(x, y):
    ix, iy = int(x - WX0), int(y - WY0)
    s = ""
    for t in tk[iy][ix]:
        s += "T" + t[0]
    if fp_[iy][ix]:
        s += "F"
    if pd[iy][ix]:
        nums = sorted({v[0] for v in pd[iy][ix]})
        lay = set()
        for v in pd[iy][ix]:
            lay.add("F" if v[1] else "")
            lay.add("B" if v[2] else "")
        s += "P(%s %s %s)" % (",".join(nums),
                              "".join(sorted(x for x in lay if x)),
                              pd[iy][ix].pop()[3])
    return s or "."


for y in range(NY):
    print("%6.1f  %s" % (WY0 + y + 0.5,
                         "  ".join("%-14s" % cell(WX0 + x + 0.5,
                                                  WY0 + y + 0.5)
                                   for x in range(NX))))

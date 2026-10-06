"""Split each net into its connected components (pads/tracks/vias).

The DRC unconnected list is a ratsnest spanning tree, not the connectivity
itself: it names *edges* and a net with 16 edges can be 2 islands or 17.  This
answers the direct question -- how many separate pieces of copper does net N
have, and what is in each piece -- so the routing work has a real target.

Touch is decided with the same primitives route-open-carrier.py uses: a pad or
via is a box, a track is a segment of radius w/2.  Two items are joined when
they share a copper layer and the distance between those shapes is <= TOL.

  python _comp.py NET [NET ...]
"""
import sys
from itertools import combinations

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
S = 1e6
TOL = 0.005          # mm; KiCad's own connectivity also joins sub-micron gaps

CU = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B"}
ALL_CU = {"F", "B"}

b = pcbnew.LoadBoard(BOARD)


def layers_of(item):
    return item[7]


# ---- shapes ----------------------------------------------------------
def pad_items(fp):
    out = []
    for p in fp.Pads():
        ls = set()
        for lid, nm in CU.items():
            if p.IsOnLayer(lid):
                ls.add(nm)
        if not ls:
            continue                      # NPTH: no copper anywhere
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            ls = ALL_CU                    # barrel joins both sides
        r = p.GetBoundingBox()
        out.append(("box", r.GetLeft() / S, r.GetTop() / S,
                    r.GetRight() / S, r.GetBottom() / S, None,
                    "%s.%s" % (fp.GetReference(), p.GetNumber()), ls))
    return out


def track_items(t):
    pos = t.GetPosition()
    if t.GetClass() == "PCB_VIA":
        x, y = pos.x / S, pos.y / S
        r = t.GetWidth(pcbnew.F_Cu) / S / 2.0
        return ("box", x - r, y - r, x + r, y + r, None, "via", ALL_CU)
    s, e = t.GetStart(), t.GetEnd()
    return ("seg", s.x / S, s.y / S, e.x / S, e.y / S,
            t.GetWidth() / S / 2.0, "trk", {CU[t.GetLayer()]})


# ---- distances -------------------------------------------------------
def d_box_box(a, c):
    dx = max(0.0, max(a[1] - c[3], c[1] - a[3]))
    dy = max(0.0, max(a[2] - c[4], c[2] - a[4]))
    return (dx * dx + dy * dy) ** 0.5


def d_pt_seg(px, py, a, c):
    x1, y1, x2, y2, r = a[1], a[2], a[3], a[4], a[5]
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5 - r


def d_pt_rect(px, py, bx):
    dx = max(0.0, max(bx[1] - px, px - bx[3]))
    dy = max(0.0, max(bx[2] - py, py - bx[4]))
    return (dx * dx + dy * dy) ** 0.5


def d_box_seg(bx, sg):
    """Segment to rectangle: zero if either endpoint is inside the rect, else
    the closest of the segment against the rect's four corners and each
    endpoint against the rect.  The minimum of those is the true distance for
    a convex pair."""
    x0, y0, x1, y1 = bx[1], bx[2], bx[3], bx[4]
    best = min(d_pt_seg(cx, cy, sg, None)
               for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    best = min(best, d_pt_rect(sg[1], sg[2], bx), d_pt_rect(sg[3], sg[4], bx))
    return best


def d_seg_seg(a, c):
    pa = ((a[1], a[2]), (a[3], a[4]))
    pc = ((c[1], c[2]), (c[3], c[4]))
    best = min(d_pt_seg(x, y, a, None) for x, y in pc)
    best = min(best, min(d_pt_seg(x, y, c, None) for x, y in pa))
    return best


def gap(a, c):
    ka, kc = a[0], c[0]
    if ka == "box" and kc == "box":
        return d_box_box(a, c)
    if ka == "seg" and kc == "seg":
        return d_seg_seg(a, c)
    return d_box_seg(a if ka == "box" else c, c if ka == "box" else a)


def touching(a, c):
    if not (layers_of(a) & layers_of(c)):
        return False
    return gap(a, c) <= TOL


# ---- union-find ------------------------------------------------------
def components(items):
    n = len(items)
    par = list(range(n))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i, j in combinations(range(n), 2):
        if touching(items[i], items[j]):
            a, c = find(i), find(j)
            if a != c:
                par[a] = c
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


for name in sys.argv[1:]:
    net = b.FindNet(name)
    if net is None:
        print("== %s: NO SUCH NET" % name)
        continue
    code = net.GetNetCode()
    items = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != code:
                continue
            ls = set()
            for lid, nm in CU.items():
                if p.IsOnLayer(lid):
                    ls.add(nm)
            if not ls:
                continue
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                ls = ALL_CU
            r = p.GetBoundingBox()
            items.append(("box", r.GetLeft() / S, r.GetTop() / S,
                          r.GetRight() / S, r.GetBottom() / S, None,
                          "%s.%s" % (fp.GetReference(), p.GetNumber()), ls))
    for t in b.GetTracks():
        if t.GetNetCode() != code:
            continue
        items.append(track_items(t))

    comps = components(items)
    comps.sort(key=lambda g: -len(g))
    print("\n== %s: %d item(s) in %d component(s)" % (name, len(items), len(comps)))
    for k, g in enumerate(comps):
        pads = sorted({items[i][6] for i in g if "." in items[i][6]})
        xs0 = min(items[i][1] - (items[i][5] or 0) for i in g)
        ys0 = min(items[i][2] - (items[i][5] or 0) for i in g)
        xs1 = max(items[i][3] + (items[i][5] or 0) for i in g)
        ys1 = max(items[i][4] + (items[i][5] or 0) for i in g)
        print("  #%d  %2d item(s)  bbox (%.2f,%.2f)-(%.2f,%.2f)" % (k, len(g), xs0, ys0, xs1, ys1))
        print("      pads: %s" % (", ".join(pads) if pads else "-"))

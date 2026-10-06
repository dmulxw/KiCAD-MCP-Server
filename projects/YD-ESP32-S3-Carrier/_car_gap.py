"""Per-net connected components on the carrier, so the open ends are named.

DRC reports unconnected_items as a *tree* of missing links, which mixes causes:
a genuine gap between two islands, a pad that nothing reaches, and a long
ratsnest edge that is really just "these two fragments are separate" -- and for
a net like +3V3 the tree can be 10 links deep with no indication of which single
fragment is the odd one out.

This groups each net's copper into what actually holds together, so the fix is
obvious: the components that must end up as one, and which pads live in which.

Geometry is sufficient here, and that is not an accident -- the copper pour has
been stripped by _car_unpour.py, so there is no zone quietly connecting two
islands that no track ties together.  (The earlier attempt at geometric
connectivity in _car_trim.py failed precisely because the pour was still on the
board: 187 GND stitch vias read as floating when they were connected through
the plane.)  With no zones, KiCad's rules reduce to what is implemented below:
tracks join where a centreline endpoint meets another centreline or falls
inside a pad or via.

  python _car_gap.py [NET ...]      # default: every net that has an open end
"""
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

EPS = 1e-4          # mm, endpoint coincidence
ON_SEG = 5e-3       # mm, endpoint-to-centreline

DROP = "--drop-orphans" in sys.argv
DRY = "--dry" in sys.argv
WANT = [a for a in sys.argv[1:] if not a.startswith("--")]

board = pcbnew.LoadBoard(BOARD)


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def seg_pt_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 <= 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5


# ---- collect ---------------------------------------------------------------
items = []      # dicts: kind, net, ...
for f in board.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        c = p.GetPosition()
        items.append({
            "kind": "pad", "net": p.GetNetname(), "obj": p, "owned": False,
            "ref": f.GetReference(), "num": str(p.GetNumber()),
            "x": pcbnew.ToMM(c.x), "y": pcbnew.ToMM(c.y),
            "x0": pcbnew.ToMM(bb.GetLeft()), "y0": pcbnew.ToMM(bb.GetTop()),
            "x1": pcbnew.ToMM(bb.GetRight()), "y1": pcbnew.ToMM(bb.GetBottom()),
            "layers": [pcbnew.LayerName(l) for l in p.GetLayerSet().Seq()
                       if l in (pcbnew.F_Cu, pcbnew.B_Cu)],
            "w": pcbnew.ToMM(p.GetSize().x), "h": pcbnew.ToMM(p.GetSize().y),
        })
for t in board.GetTracks():
    net = t.GetNetname()
    par = t.GetParent()
    owned = par is not None and par.GetClass() == "FOOTPRINT"
    if t.GetClass() == "PCB_VIA":
        c = t.GetPosition()
        items.append({"kind": "via", "net": net, "obj": t, "owned": owned,
                      "x": pcbnew.ToMM(c.x), "y": pcbnew.ToMM(c.y),
                      "w": pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))})
    else:
        s, e = t.GetStart(), t.GetEnd()
        items.append({
            "kind": "track", "net": net, "obj": t, "owned": owned,
            "x1": pcbnew.ToMM(s.x), "y1": pcbnew.ToMM(s.y),
            "x2": pcbnew.ToMM(e.x), "y2": pcbnew.ToMM(e.y),
            "w": pcbnew.ToMM(t.GetWidth()),
            "layer": pcbnew.LayerName(t.GetLayer()),
        })

# ---- union -----------------------------------------------------------------
dsu = DSU(len(items))
by_net = {}
for i, it in enumerate(items):
    by_net.setdefault(it["net"], []).append(i)


def layers_overlap(track, pad):
    return track["layer"] in pad["layers"]


def covers(it, x, y):
    """Does this item's copper contain point (x, y)?"""
    if it["kind"] == "track":
        return seg_pt_dist(x, y, it["x1"], it["y1"], it["x2"], it["y2"]) \
            <= it["w"] / 2 + ON_SEG
    r = it["w"] / 2
    return (x - it["x"]) ** 2 + (y - it["y"]) ** 2 <= (r + ON_SEG) ** 2


for net, idxs in by_net.items():
    for a in range(len(idxs)):
        ia = items[idxs[a]]
        for b in range(a + 1, len(idxs)):
            ib = items[idxs[b]]
            # layers must overlap for copper to touch
            if ia["kind"] == "track" and ib["kind"] == "track" \
                    and ia["layer"] != ib["layer"]:
                continue
            joined = False
            if ia["kind"] == "track" and ib["kind"] == "track":
                # endpoint of one landing on the other's centreline
                for (px, py) in ((ia["x1"], ia["y1"]), (ia["x2"], ia["y2"])):
                    if seg_pt_dist(px, py, ib["x1"], ib["y1"],
                                   ib["x2"], ib["y2"]) <= ON_SEG:
                        joined = True
                        break
                if not joined:
                    for (px, py) in ((ib["x1"], ib["y1"]), (ib["x2"], ib["y2"])):
                        if seg_pt_dist(px, py, ia["x1"], ia["y1"],
                                       ia["x2"], ia["y2"]) <= ON_SEG:
                            joined = True
                            break
            elif ia["kind"] == "track" or ib["kind"] == "track":
                tr, other = (ia, ib) if ia["kind"] == "track" else (ib, ia)
                if other["kind"] == "via":
                    # a through via is copper on both layers, so the track's
                    # layer never disqualifies the pair
                    for (px, py) in ((tr["x1"], tr["y1"]), (tr["x2"], tr["y2"])):
                        if covers(other, px, py):
                            joined = True
                            break
                elif layers_overlap(tr, other):  # pad, and the track can reach it
                    for (px, py) in ((tr["x1"], tr["y1"]),
                                     (tr["x2"], tr["y2"])):
                        if (other["x0"] - ON_SEG <= px <= other["x1"] + ON_SEG
                                and other["y0"] - ON_SEG <= py
                                <= other["y1"] + ON_SEG):
                            joined = True
                            break
            else:
                # pad/via pair: bounding-box containment of the smaller centre
                d = ((ia["x"] - ib["x"]) ** 2 + (ia["y"] - ib["y"]) ** 2) ** 0.5
                if ia["kind"] == "via" and ib["kind"] == "pad":
                    if (ib["x0"] <= ia["x"] <= ib["x1"]
                            and ib["y0"] <= ia["y"] <= ib["y1"]):
                        joined = True
                elif ib["kind"] == "via" and ia["kind"] == "pad":
                    if (ia["x0"] <= ib["x"] <= ia["x1"]
                            and ia["y0"] <= ib["y"] <= ia["y1"]):
                        joined = True
                else:
                    # both vias: copper touches when their discs overlap
                    if d <= (ia["w"] + ib["w"]) / 2 + ON_SEG:
                        joined = True
            if joined:
                dsu.union(idxs[a], idxs[b])


# ---- report ----------------------------------------------------------------
def groups_for(net):
    idxs = by_net.get(net, [])
    g = {}
    for i in idxs:
        g.setdefault(dsu.find(i), []).append(i)
    return list(g.values())


nets = WANT or sorted(
    n for n in by_net
    if n and len(groups_for(n)) > 1
)
tot = 0
for net in nets:
    gs = groups_for(net)
    if len(gs) < 2:
        print("%s: already one piece" % net)
        continue
    tot += len(gs) - 1
    print("\n%s -- %d separate piece(s)" % (net, len(gs)))
    for k, g in enumerate(sorted(gs, key=lambda g: -len(g)), 1):
        pads = [items[i] for i in g if items[i]["kind"] == "pad"]
        trks = sum(1 for i in g if items[i]["kind"] == "track")
        vias = sum(1 for i in g if items[i]["kind"] == "via")
        xs = [items[i].get("x", items[i].get("x1")) for i in g]
        ys = [items[i].get("y", items[i].get("y1")) for i in g]
        print("  [%d] %2d item(s): %d track %d via %d pad   x %.1f..%.1f  y %.1f..%.1f"
              % (k, len(g), trks, vias, len(pads),
                 min(xs), max(xs), min(ys), max(ys)))
        for p in sorted(pads, key=lambda p: p["ref"]):
            print("        %-4s.%-3s (%.2f, %.2f) %s"
                  % (p["ref"], p["num"], p["x"], p["y"], ",".join(p["layers"])))

print("\n%d net(s) split; %d missing link(s) minimum" % (len(nets), tot))

# ---- orphan sweep ----------------------------------------------------------
# A component holding no pad of its net is dead copper: it reaches nothing, so
# by construction it cannot be part of any connection, and no amount of routing
# elsewhere will give it one.  On this board they are exactly the runs that used
# to land on a 595 pin -- the strip's fan-out, orphaned when U3-U6 were deleted.
#
# Deleting is the whole fix for those, but only for those.  A component that
# *does* hold a pad is kept even if it is lonely, because it is the thing a
# route still has to reach, and deleting it would just move the problem.
#
# Footprint-owned copper (U1's thermal vias) is never touched: it belongs to the
# footprint, and it is padless only because the pour that used to tie it to GND
# is currently stripped.
if DROP:
    doomed = []
    for net, idxs in by_net.items():
        if not net:
            continue
        for g in groups_for(net):
            if any(items[i]["kind"] == "pad" for i in g):
                continue
            doomed.extend(items[i] for i in g if not items[i]["owned"])

    print("\n--drop-orphans: %d padless copper item(s) across %d net(s)"
          % (len(doomed), len({d["net"] for d in doomed})))
    byn = {}
    for d in doomed:
        byn.setdefault(d["net"], []).append(d)
    for n in sorted(byn):
        xs = [d.get("x", d.get("x1")) for d in byn[n]]
        ys = [d.get("y", d.get("y1")) for d in byn[n]]
        print("   %-8s %3d item(s)  x %.1f..%.1f  y %.1f..%.1f"
              % (n, len(byn[n]), min(xs), max(xs), min(ys), max(ys)))

    if DRY:
        print("\ndry run -- nothing written")
    else:
        import shutil
        backup = BOARD + ".pre-orphan.bak"
        shutil.copyfile(BOARD, backup)
        print("\nbackup -> %s" % backup)
        _keep_alive = []
        for d in doomed:
            board.Remove(d["obj"])
            _keep_alive.append(d["obj"])
        board.Save(BOARD)
        after = pcbnew.LoadBoard(BOARD)
        print("saved: %d track/via item(s)  (%d -> %d)"
              % (len(list(after.GetTracks())), len(items),
                 len(list(after.GetTracks()))))

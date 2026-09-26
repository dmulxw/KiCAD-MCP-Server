"""Bridge the intra-net islands the rip left behind.

_r2.kicad_pcb routes all 40 header pins out and emits no illegal copper, yet
DRC still reports 82 unconnected items.  Those are not missing routes -- not
one of them names a J1A/J1B pad.  They are fragments of the OLD fan-out, cut
loose when the fan-out was ripped.  Every entry pairs two pieces of the *same*
net: a pull-down pad against a track stub (ROW5: R6.1 <-> 2.2114mm) or two
track stubs against each other (ROW3: 0.4244mm <-> 1.9225mm).

So the job is stitching, not routing: for each fragmented net, find its
connected components and bridge every orphan back to the largest one.  The
search is route40's -- same NGrid, same astar, same emitter, and therefore the
same corrected distance field (probe.item_seg), which is what makes a bridge
safe to emit rather than another short.

A net is bridged against a grid built from every OTHER net, so one net's
finished bridges are obstacles to the next net's.  Ordering therefore matters
and is not free; --order picks it, --dry reports the island census so the
choice is made from measurement rather than from the net's name.

    python stitch.py --dry
    python stitch.py --order small --out _s1.kicad_pcb
"""
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import emitlib as M                                                  # noqa: E402
import probe, replan                                                 # noqa: E402

S = 1e6
LAYERS = M.LAYERS

SRC = os.environ.get("SRC", "_r2.kicad_pcb")
OUT = os.environ.get("OUT", "_s1.kicad_pcb")
DRC = os.environ.get("DRC", "_drc_r2.json")
DRY = "--dry" in sys.argv
ORDER = "large"
if "--order" in sys.argv:
    ORDER = sys.argv[sys.argv.index("--order") + 1]
ONLY = []
if "--nets" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--nets") + 1:]


# ---------------------------------------------------------------- islands
def islands(items, netname):
    """Connected components of one net's copper, largest first.

    Based on final.py's, but with KiCad's own joining rule rather than "copper
    that touches".  KiCad connects two tracks when an *endpoint* of one lands
    within the other's copper; overlapping copper is not enough, and
    sum-of-half-widths is the wrong test in the expensive direction.  It merges
    a sub-half-width near-miss into one island, the net then looks whole,
    nothing is bridged, and DRC reports the fragments anyway -- which is
    exactly what CSEL2 and ROW17 did on _r2: a 0.0636mm B.Cu stub and a
    0.0460mm F.Cu stub, the two ends of a via the rip removed, read as one
    island and so were never bridged.

    Erring strict is safe.  A split KiCad would call whole costs one redundant
    bridge, and a same-net bridge cannot short anything; a bad merge costs a
    net that DRC keeps reporting.
    """
    g = [it for it in items if it.GetNetname() == netname]
    par = list(range(len(g)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra

    def is_pad(it):
        return isinstance(it, pcbnew.PAD)

    def ends(it):
        """The points that must land inside the other item's copper.

        A via's Start and End are both its centre, which is the right answer:
        a track reaches a via when its endpoint falls inside the via's disc.
        """
        s, e = it.GetStart(), it.GetEnd()
        return (s.x / S, s.y / S), (e.x / S, e.y / S)

    def rad(it):
        """Half-width, or a via's radius.  GetWidth() asserts on PCB_VIA."""
        if isinstance(it, pcbnew.PCB_VIA):
            return it.GetBoundingBox().GetWidth() / S / 2
        return it.GetWidth() / S / 2

    def box(it):
        bb = it.GetBoundingBox()
        return (bb.GetLeft() / S, bb.GetTop() / S,
                bb.GetRight() / S, bb.GetBottom() / S)

    def d_pt_seg(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == 0 and dy == 0:
            return ((x - a[0]) ** 2 + (y - a[1]) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        return ((x - (a[0] + t * dx)) ** 2 + (y - (a[1] + t * dy)) ** 2) ** 0.5

    def d_ss(p, q, r, s):
        return min(d_pt_seg(p[0], p[1], r, s), d_pt_seg(q[0], q[1], r, s),
                   d_pt_seg(r[0], r[1], p, q), d_pt_seg(s[0], s[1], p, q))

    def reaches(P, Q):
        """Does any endpoint of P land inside Q's copper?  P is not a pad."""
        lim = rad(Q) + 1e-6
        qa, qb = ends(Q)
        return any(d_pt_seg(p[0], p[1], qa, qb) <= lim for p in ends(P))

    for a in range(len(g)):
        for b in range(a + 1, len(g)):
            A, B = g[a], g[b]
            apa, bpa = is_pad(A), is_pad(B)
            if not apa and not bpa:
                if not any(A.IsOnLayer(l) and B.IsOnLayer(l) for l in LAYERS):
                    continue
                if not (reaches(A, B) or reaches(B, A)):
                    continue
            elif apa and bpa:
                # Pad-to-pad: a shared GND/PWR cluster of through-hole pads.
                # Bounding boxes, because two pads that overlap in copper really
                # are one node and there is no centreline to test against.
                ax0, ay0, ax1, ay1 = box(A)
                bx0, by0, bx1, by1 = box(B)
                if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
                    continue
            else:
                pad, oth = (A, B) if apa else (B, A)
                # The pad's own shape test, not its bounding box: a round 1.7mm
                # header pad's bbox has corners 0.35mm outside the metal, and a
                # track ending there is not connected to anything.
                if not any(pad.IsOnLayer(oth.GetLayer())
                           and pad.HitTest(pcbnew.VECTOR2I(int(round(p[0] * S)),
                                                           int(round(p[1] * S))))
                           for p in ends(oth)):
                    # ...or the pad's centre lying inside the track's copper,
                    # which is how a track passing under a pad connects.
                    c = pad.GetPosition()
                    oa, ob = ends(oth)
                    if (d_pt_seg(c.x / S, c.y / S, oa, ob) > rad(oth) + 1e-6
                            or not pad.IsOnLayer(oth.GetLayer())):
                        continue
            uni(a, b)
    groups = {}
    for i in range(len(g)):
        groups.setdefault(find(i), []).append(i)
    return g, sorted(groups.values(), key=len, reverse=True)


def bbox_of(g, grp):
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for k in grp:
        bb = g[k].GetBoundingBox()
        x0 = min(x0, bb.GetLeft() / S)
        y0 = min(y0, bb.GetTop() / S)
        x1 = max(x1, bb.GetRight() / S)
        y1 = max(y1, bb.GetBottom() / S)
    return x0, y0, x1, y1


def bbox_gap(a, b):
    """Distance between two bounding boxes; 0 if they overlap.

    Only used to order the orphans, so the cheap box-to-box number is enough --
    the A* that follows picks the true nearest goal among all of them.
    """
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------- target nets
def pairs_from_drc(path):
    d = json.load(open(path, encoding="utf-8"))
    cnt = collections.Counter()
    for it in d.get("unconnected_items", []):
        for e in it.get("items", []):
            desc = e.get("description", "")
            if "[" in desc and "]" in desc:
                cnt[desc.split("[", 1)[1].split("]", 1)[0]] += 1
    return cnt


cnt = pairs_from_drc(DRC)
targets = [(n, c // 2) for n, c in cnt.most_common()]
if ONLY:
    targets = [t for t in targets if t[0] in ONLY]
print("%s: %d net(s) fragmented, %d item(s) unconnected"
      % (DRC, len(targets), 2 * sum(c for _, c in targets)), flush=True)

board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)
print("%s  step=%.2f keep=%.3f pad_keep=%.3f egk=%.3f vek=%.3f"
      % (SRC, M.step, M.keep, M.pad_keep, M.egk, M.vek), flush=True)


def census():
    """net -> (items, groups) for every target net, on the current board."""
    allc = M.fresh()
    out = {}
    for name, npair in targets:
        g, groups = islands(allc, name)
        if len(groups) > 1:
            out[name] = (g, groups)
    return out


cen = census()
print("\nisland census (targets with >1 island):", flush=True)
for name, npair in targets:
    if name not in cen:
        print("  %-7s %2d pair(s)   already ONE island (nothing to stitch)"
              % (name, npair), flush=True)
        continue
    g, groups = cen[name]
    print("  %-7s %2d pair(s)   %d island(s)  sizes %s"
          % (name, npair, len(groups), [len(x) for x in groups[:6]]), flush=True)
    for k, grp in enumerate(groups):
        x0, y0, x1, y1 = bbox_of(g, grp)
        print("      %-6s %3d item(s)  x %8.3f..%8.3f  y %8.3f..%8.3f"
              % ("main" if k == 0 else "#%d" % k, len(grp), x0, x1, y0, y1), flush=True)

if DRY:
    print("\n--dry: nothing written", flush=True)
    sys.exit(0)

# ---------------------------------------------------------------- stitching
if ORDER == "small":
    work = sorted(cen.items(), key=lambda kv: len(kv[1][1]))
elif ORDER == "large":
    work = sorted(cen.items(), key=lambda kv: -len(kv[1][1]))
else:
    work = [(n, cen[n]) for n in ONLY if n in cen]
print("\nstitching in --order %s: %s"
      % (ORDER, " ".join("%s(%d)" % (n, len(gs)) for n, (_, gs) in work)), flush=True)

total_ok = total_no = 0
total_len = 0.0
worst = (0.0, None, 0)
t0 = time.time()
for name, (g, groups) in work:
    # Re-read every time: the previous net's bridges are obstacles for this one.
    allc = M.fresh()
    obstacles = [it for it in allc if it.GetNetname() != name]
    grid = M.make_grid(obstacles)
    main = groups[0]
    goals = M.goals_of(grid, [g[i] for i in main])
    print("\n%-7s %d island(s), main %d item(s), %d goal cell(s)"
          % (name, len(groups), len(main), len(goals)), flush=True)
    if not goals:
        print("   main island covers no legal cell -- skipped", flush=True)
        continue
    # Nearest-first, against a component that grows.
    #
    # A* returns the cheapest path to ANY goal, so how long a bridge is depends
    # on which orphan runs first, not on the search.  With `goals` frozen at the
    # main island, every orphan searches the whole board back to one small blob:
    # measured on _r2 that gave GND bridges of 66.1, 72.5, 104.1, 133.3 and
    # 136.0mm -- and the bridges ate the left gutter, which is the corridor
    # every ROW net has to use, so the last stub came back NO PATH.
    #
    # Taking the nearest orphan first and adding its cells to `goals` the
    # moment it is joined turns the same work into a chain: GND's 19 stubs sit
    # 6.4mm apart in the left gutter, so each one hops 6.4mm to the stub the
    # previous bridge just absorbed, and the top strip and bottom strip come in
    # at the end for a few mm each.  Same copper, a fraction of the length.
    comp = [g[i] for i in main]
    cb = bbox_of(g, main)
    order = sorted(range(1, len(groups)),
                   key=lambda k: bbox_gap(cb, bbox_of(g, groups[k])))
    for k in order:
        grp = groups[k]
        st = [c for c in replan.cells_of(grid, [g[i] for i in grp], LAYERS)
              if grid.OK[c[0]][c[2], c[1]]]
        if not st:
            # Copper too thin to cover a legal cell: fall back to the legal
            # cells ringing the fragment's endpoints (final.py's rescue).
            for idx in grp:
                it = g[idx]
                if not isinstance(it, pcbnew.PCB_TRACK):
                    continue
                s, e = it.GetStart(), it.GetEnd()
                for pt in (s, e):
                    i, j = grid.ij(pt.x / S, pt.y / S)
                    for l in LAYERS:
                        for di in (-1, 0, 1):
                            for dj in (-1, 0, 1):
                                a, b = i + di, j + dj
                                if (0 <= a < grid.nx and 0 <= b < grid.ny
                                        and grid.OK[l][b, a]):
                                    st.append((l, a, b))
        st = list(dict.fromkeys(st))[:16]
        if not st:
            print("   island %-2d (%2d item(s)): no legal start cell"
                  % (k, len(grp)), flush=True)
            total_no += 1
            continue
        path, cross, exp, closest = probe.astar(grid, st, goals, 25.0, conflict=False)
        if path is None:
            x0, y0, x1, y1 = bbox_of(g, grp)
            print("   island %-2d (%2d item(s)) x %7.3f..%7.3f y %7.3f..%7.3f: "
                  "NO PATH (closest %.2fmm, %d expanded)"
                  % (k, len(grp), x0, x1, y0, y1, closest[0] * M.step, exp), flush=True)
            total_no += 1
            continue
        ln = sum(((path[q][1] - path[q - 1][1]) ** 2
                  + (path[q][2] - path[q - 1][2]) ** 2) ** 0.5
                 for q in range(1, len(path))) * M.step
        p0 = grid.xy(path[0][1], path[0][2])
        p1 = grid.xy(path[-1][1], path[-1][2])
        a0 = M.attach_pt(p0[0], p0[1], [g[i] for i in grp])
        # Attach the far end to the component as it stands now, which is the
        # copper the path actually reached -- not just to the original main.
        a1 = M.attach_pt(p1[0], p1[1], comp)
        pre = (a0[0], a0[1], path[0][0]) if a0 else None
        post = (a1[0], a1[1], path[-1][0]) if a1 else None
        nt, nv, nr = M.emit(name, grid, path, pre=pre, post=post)
        print("   island %-2d (%2d item(s)) -> comp: %6.1fmm  %2d trk %d via"
              % (k, len(grp), ln, nt, nv), flush=True)
        # Joined: its copper is now part of the component, so it becomes a goal
        # for everything still to come -- this is what makes the chain work.
        comp.extend(g[i] for i in grp)
        cb = (min(cb[0], bbox_of(g, grp)[0]), min(cb[1], bbox_of(g, grp)[1]),
              max(cb[2], bbox_of(g, grp)[2]), max(cb[3], bbox_of(g, grp)[3]))
        goals |= {c for c in replan.cells_of(grid, [g[i] for i in grp], LAYERS)
                  if grid.OK[c[0]][c[2], c[1]]}
        total_ok += 1
        total_len += ln
        worst = max(worst, (ln, name, k))

print("\nbridged %d island(s), %d unreachable, %.1fmm of new copper, %.1fs"
      % (total_ok, total_no, total_len, time.time() - t0), flush=True)
if worst[1]:
    print("longest single bridge: %.1fmm (%s island %d)" % worst, flush=True)
board.Save(OUT)
print("saved %s" % OUT, flush=True)

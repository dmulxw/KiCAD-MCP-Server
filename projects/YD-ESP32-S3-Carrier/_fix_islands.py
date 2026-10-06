"""Stitch the GND pour islands that DRC calls unconnected.

The 4 mm stitching lattice in pour.py is laid *before* the fill, on a fixed grid,
and skips any point that has copper near it.  That is fine where the board is
open, but it means the lattice has holes exactly where the routing is densest --
and a hole in the lattice is a place the two layers' pour cannot meet.  Where
such a hole lands inside a pocket of F.Cu surrounded by traces, the pocket is
stranded: one island, touching nothing but its own layer.

DRC reports each stranded pair, but a zone item's `pos` in the report is the
zone outline origin -- (0.50, 0.50) for every island -- so the report cannot say
where they are.  _probe_islands.py measures them instead: rasterise the filled
copper at 0.2 mm, flood-fill the components, union across the layers at every
via and through-hole pad, and the connected groups of *that* are the islands.

Repair, in two grades.  First a via inside a stranded island whose opposite-layer
copper is already part of the main island -- one via and the island is home, and
that is what most of them need.  When there is no such cell the pocket is the
only GND copper for millimetres around, so no via can help; then the plane may
still be a fraction of a millimetre away across bare board, and the second grade
is a short track to it (track_for).  Both are re-measured every pass, because
each one changes which islands are still stranded.

  python _fix_islands.py <in.kicad_pcb> <out.kicad_pcb> [--dry]
"""
import sys
from collections import deque

import pcbnew

BASE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
sys.path.insert(0, BASE + r"\scripts")
import pour as P  # noqa: E402  (importable: pour.main() is guarded)

GRID = 0.20
STRIDE = 3              # (unused: candidates are ranked by centroid distance)
TRACK_W = 0.30          # the repair track, when a via will not do
BW, BH = 100.0, 74.0
NX = int(BW / GRID) + 1
NY = int(BH / GRID) + 1
FROM = pcbnew.FromMM
TO = pcbnew.ToMM
LAY = (pcbnew.F_Cu, pcbnew.B_Cu)


def raster(board):
    """One bytearray per layer: 1 where that layer's GND pour has copper."""
    out = {}
    for l in LAY:
        buf = bytearray(NX * NY)
        for z in P.fill_zones(board, l):
            bb = z.GetBoundingBox()
            i0 = max(0, int(TO(bb.GetLeft()) / GRID))
            i1 = min(NX - 1, int(TO(bb.GetRight()) / GRID) + 1)
            j0 = max(0, int(TO(bb.GetTop()) / GRID))
            j1 = min(NY - 1, int(TO(bb.GetBottom()) / GRID) + 1)
            for i in range(i0, i1 + 1):
                x = FROM(i * GRID)
                for j in range(j0, j1 + 1):
                    k = j * NX + i
                    if not buf[k] and z.HitTestFilledArea(
                            l, pcbnew.VECTOR2I(x, FROM(j * GRID))):
                        buf[k] = 1
        out[l] = buf
    return out


def label(buf):
    """8-connected components -- diagonal neighbours count.

    Four-connectivity would split any neck that crosses a cell corner, and a
    spurious island costs a via and a second look at DRC.  The pose here is
    conservative in the direction that matters: over-counting a *connection* is
    only possible where two pours genuinely touch at a corner, which the filler
    does not produce with a 0.20 mm clearance between nets.
    """
    ids = [-1] * (NX * NY)
    boxes = []
    n = 0
    for start in range(NX * NY):
        if not buf[start] or ids[start] >= 0:
            continue
        stack = [start]
        ids[start] = n
        i0 = i1 = start % NX
        j0 = j1 = start // NX
        while stack:
            c = stack.pop()
            i, j = c % NX, c // NX
            i0, i1 = min(i0, i), max(i1, i)
            j0, j1 = min(j0, j), max(j1, j)
            for di in (-1, 0, 1):
                ii = i + di
                if not (0 <= ii < NX):
                    continue
                for dj in (-1, 0, 1):
                    jj = j + dj
                    if not (0 <= jj < NY):
                        continue
                    k = jj * NX + ii
                    if buf[k] and ids[k] < 0:
                        ids[k] = n
                        stack.append(k)
        boxes.append((i0 * GRID, i1 * GRID, j0 * GRID, j1 * GRID))
        n += 1
    return ids, n, boxes


def main(src, dst, dry):
    board = pcbnew.LoadBoard(src)
    if board is None:
        sys.exit("LoadBoard returned None for " + src)

    buf = raster(board)
    comp = {}
    for l in LAY:
        ids, n, boxes = label(buf[l])
        buf[l] = ids
        for c in range(n):
            comp[(l, c)] = 0
        # count the cells, so "largest island" means largest copper
        for v in ids:
            if v >= 0:
                comp[(l, v)] += 1
        for c in range(n):
            comp[(l, c, "bbox")] = boxes[c]
        print("  %-5s %4d component(s)" %
              ("F.Cu" if l == pcbnew.F_Cu else "B.Cu", n))

    def cell_of(l, x, y, reach=2):
        """The component of `l` at (x, y), probing a small disc: a via centre is
        a hole in the pour, so the point itself is usually empty."""
        i, j = int(round(x / GRID)), int(round(y / GRID))
        for r in range(reach + 1):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    ii, jj = i + di, j + dj
                    if 0 <= ii < NX and 0 <= jj < NY:
                        v = buf[l][jj * NX + ii]
                        if v >= 0:
                            return v
        return -1

    keys = [k for k in comp if len(k) == 2]
    other = {pcbnew.F_Cu: pcbnew.B_Cu, pcbnew.B_Cu: pcbnew.F_Cu}
    netcode = P.gnd_netcode(board)
    parent = {}

    def find(a):
        while parent.get(a, a) != a:
            parent[a] = parent.get(parent[a], parent[a])
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    def reconnect():
        """Rebuild the union from the board as it stands now.

        The raster is measured once, before any via is added: a GND via dropped
        into a GND pour does not move the pour, it welds to it.  What changes is
        which pieces are *joined*, and that is all this recomputes.  Re-rastering
        per pass would cost 24 s to learn nothing.
        """
        parent.clear()
        for k in keys:
            parent[k] = k
        # The only points where the two rasters can meet: a via, a pad with
        # copper on both layers, or the two ends of a track.
        for t in board.GetTracks():
            if t.GetNetname() != "GND":
                continue
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                got = [(l, c) for l in LAY
                       for c in [cell_of(l, TO(p.x), TO(p.y))] if c >= 0]
                for g in got[1:]:
                    union(got[0], g)
                continue
            # A trace carries one component at each end, and *different* ones --
            # that join is the whole point of the repair track below, so it has
            # to be visible here or the next pass would lay it again.
            ends = []
            for v in (t.GetStart(), t.GetEnd()):
                c = cell_of(t.GetLayer(), TO(v.x), TO(v.y))
                if c >= 0:
                    ends.append((t.GetLayer(), c))
            for g in ends[1:]:
                union(ends[0], g)
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if str(p.GetNetname()) != "GND":
                    continue
                if not (p.IsOnLayer(pcbnew.F_Cu) and p.IsOnLayer(pcbnew.B_Cu)):
                    continue
                pos = p.GetPosition()
                x, y = TO(pos.x), TO(pos.y)
                got = [(l, c) for l in LAY for c in [cell_of(l, x, y)] if c >= 0]
                for g in got[1:]:
                    union(got[0], g)
        groups = {}
        for k in keys:
            groups.setdefault(find(k), []).append(k)
        sizes = {r: sum(comp[m] for m in ms) for r, ms in groups.items()}
        home = max(sizes, key=sizes.get)
        return groups, sizes, home

    def spot_for(members, home):
        """A cell inside `members` whose opposite-layer copper is already home.

        Gathered first, because the fit test is cheap and the exact one is not:
        free_for_via() walks every pad and every track, so calling it per cell
        turns a 122 mm2 island into 3000 full board scans.  Cells are then tried
        from the island's middle outwards -- an interior cell is the one most
        likely to be clear, because the copper that stranded the island runs
        along its edge.
        """
        cand = []
        for (l, c) in members:
            x0, x1, y0, y1 = comp[(l, c, "bbox")]
            i0, i1 = int(x0 / GRID), int(x1 / GRID)
            j0, j1 = int(y0 / GRID), int(y1 / GRID)
            ci, cj = (i0 + i1) / 2.0, (j0 + j1) / 2.0
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    if buf[l][j * NX + i] != c:
                        continue
                    o = buf[other[l]][j * NX + i]
                    if o < 0 or find((other[l], o)) != home:
                        continue
                    cand.append((((i - ci) ** 2 + (j - cj) ** 2), l, i, j))
        cand.sort()
        for (_, l, i, j) in cand[:80]:
            x, y = i * GRID, j * GRID
            if P.free_for_via(board, x, y):
                return (x, y)
        return None

    def clear_corridor(l, x1, y1, x2, y2, w):
        """Nothing foreign within w/2 + CLEAR of the centreline.

        The half-width is the point: a track's copper reaches w/2 either side of
        its centre, and the design rule demands CLEAR beyond that.  So the test
        is a disc of radius w/2 + CLEAR swept along the line -- the same shape
        the DRC will measure, only cheaper.  GND copper is skipped: touching the
        pour it is joining is the entire job.
        """
        acc = FROM(w / 2.0 + P.CLEAR)
        L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        steps = max(1, int(L / 0.05) + 1)
        for s in range(steps + 1):
            f = s / float(steps)
            pos = pcbnew.VECTOR2I(FROM(x1 + (x2 - x1) * f),
                                  FROM(y1 + (y2 - y1) * f))
            for it in board.GetTracks():
                if it.GetNetname() == "GND" or not it.IsOnLayer(l):
                    continue
                if it.HitTest(pos, acc):
                    return "%s track at (%.2f,%.2f)" % (
                        str(it.GetNetname()) or "-", TO(pos.x), TO(pos.y))
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if str(pad.GetNetname()) == "GND" or not pad.IsOnLayer(l):
                        continue
                    if pad.HitTest(pos, acc):
                        return "%s.%s at (%.2f,%.2f)" % (
                            str(fp.GetReference()), str(pad.GetNumber()),
                            TO(pos.x), TO(pos.y))
        return None

    def track_for(members, home):
        """A track to the nearest home copper on the island's *own* layer.

        The via search needs the opposite layer to be already home.  When it is
        not, the pocket is the only GND copper for millimetres in every direction
        and no via can help -- but the plane may still be a fraction of a
        millimetre away across bare board, which is what a track is for.

        Distance comes from a BFS seeded at every home cell on that layer, so
        "nearest" is free space rather than straight line; the corridor test then
        decides whether the shortest one is actually buildable.
        """
        out = []
        blame = []
        # One BFS per layer the group has a piece on.  Seeding from the *first*
        # member's layer is the trap: J4.7's pocket is 7 mm2 on F.Cu and 9.6 on
        # B.Cu, and the F.Cu side is walled in by another net while the B.Cu side
        # is 0.6 mm of bare board -- searching only F.Cu reports "no route" for a
        # pocket that has one.
        for l in sorted(set(m[0] for m in members)):
            ids = buf[l]
            N = NX * NY
            dist = [-1] * N
            src = [-1] * N
            q = deque()
            for k in range(N):
                if ids[k] >= 0 and find((l, ids[k])) == home:
                    dist[k] = 0
                    src[k] = k
                    q.append(k)
            if not q:
                continue
            while q:
                k = q.popleft()
                i, j = k % NX, k // NX
                for di in (-1, 0, 1):
                    ii = i + di
                    if not (0 <= ii < NX):
                        continue
                    for dj in (-1, 0, 1):
                        jj = j + dj
                        if not (0 <= jj < NY):
                            continue
                        kk = jj * NX + ii
                        if dist[kk] < 0:
                            dist[kk] = dist[k] + 1
                            src[kk] = src[k]
                            q.append(kk)
            # Gather several, not just the nearest.  The closest home copper is
            # often the one behind a trace, and the second-closest is a tenth of
            # a millimetre further for a clear run at it.
            cand = []
            for (ml, c) in members:
                if ml != l:
                    continue
                x0, x1, y0, y1 = comp[(l, c, "bbox")]
                for i in range(int(x0 / GRID), int(x1 / GRID) + 1):
                    for j in range(int(y0 / GRID), int(y1 / GRID) + 1):
                        k = j * NX + i
                        if buf[l][k] != c or dist[k] < 0:
                            continue
                        cand.append((dist[k], i, j, src[k]))
            cand.sort()
            for (_, i, j, k2) in cand[:60]:
                ax, ay = i * GRID, j * GRID
                bx, by = (k2 % NX) * GRID, (k2 // NX) * GRID
                L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
                if L < 1e-6:
                    continue
                ux, uy = (bx - ax) / L, (by - ay) / L
                # Bury each end inside its own pour.  The segment already crosses
                # the island cell and the home cell, so it is connected either
                # way; this just stops an endpoint landing a hair outside the
                # fill.
                p1 = (ax - ux * 0.30, ay - uy * 0.30)
                p2 = (bx + ux * 0.30, by + uy * 0.30)
                why = clear_corridor(l, p1[0], p1[1], p2[0], p2[1], TRACK_W)
                if why is None:
                    out.append((l, p1[0], p1[1], p2[0], p2[1], L))
                    break
                blame.append((L, why))
        if not out:
            for L, why in sorted(blame)[:3]:
                print("      no track: %.2f mm run blocked by %s" % (L, why))
        return min(out, key=lambda s: s[5]) if out else None

    # One pass is not enough.  An island whose only opposite-layer copper is
    # another *stranded* island cannot be joined until that one is home, so each
    # pass lifts the islands that can reach the growing main group and the next
    # pass gets the ones it unlocked.
    keep = []                       # every added proxy, alive until the save
    added = 0
    for p in range(1, 7):
        groups, sizes, home = reconnect()
        stranded = [r for r in sizes if r != home]
        print("  pass %d: %d island(s), largest %.0f mm2, %d stranded"
              % (p, len(sizes), sizes[home] * GRID * GRID, len(stranded)))
        if not stranded:
            break
        done = 0
        for r in stranded:
            spot = spot_for(groups[r], home)
            if spot:
                print("    via at (%6.2f,%6.2f) joins a %.1f mm2 island"
                      % (spot[0], spot[1], sizes[r] * GRID * GRID))
                if not dry:
                    keep.append(P.add_stitch(board, netcode, spot[0], spot[1]))
                added += 1
                done += 1
                continue
            seg = track_for(groups[r], home)
            if not seg:
                continue
            l, ax, ay, bx, by, L = seg
            print("    %s track (%6.2f,%6.2f) -> (%6.2f,%6.2f) %.2f mm joins a "
                  "%.1f mm2 island"
                  % ("F.Cu" if l == pcbnew.F_Cu else "B.Cu", ax, ay, bx, by, L,
                     sizes[r] * GRID * GRID))
            if not dry:
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pcbnew.VECTOR2I(FROM(ax), FROM(ay)))
                tr.SetEnd(pcbnew.VECTOR2I(FROM(bx), FROM(by)))
                tr.SetWidth(FROM(TRACK_W))
                tr.SetLayer(l)
                tr.SetNetCode(netcode)
                board.Add(tr)
                keep.append(tr)
            added += 1
            done += 1
        if not done:
            for r in stranded:
                xs = [comp[m + ("bbox",)] for m in groups[r]]
                print("    %.1f mm2 island at x %6.2f..%6.2f y %6.2f..%6.2f has "
                      "no direct spot"
                      % (sizes[r] * GRID * GRID, min(b[0] for b in xs),
                         max(b[1] for b in xs), min(b[2] for b in xs),
                         max(b[3] for b in xs)))
                # Say what *is* under it, so "boxed in" is a measurement and not
                # a shrug: an island ringed by empty B.Cu needs a different fix
                # from one whose far side is another stranded island.
                tally = {}
                for (l, c) in groups[r]:
                    x0, x1, y0, y1 = comp[(l, c, "bbox")]
                    for i in range(int(x0 / GRID), int(x1 / GRID) + 1):
                        for j in range(int(y0 / GRID), int(y1 / GRID) + 1):
                            if buf[l][j * NX + i] != c:
                                continue
                            o = buf[other[l]][j * NX + i]
                            k = ("empty" if o < 0 else
                                 ("home" if find((other[l], o)) == home
                                  else "island %.1f" % (
                                      sizes[find((other[l], o))] * GRID * GRID)))
                            tally[k] = tally.get(k, 0) + 1
                for k, v in sorted(tally.items(), key=lambda kv: -kv[1])[:6]:
                    print("        far side over %5d cell(s): %s" % (v, k))
            break

    if dry:
        print("\ndry run: %d via(s) would be placed" % added)
        return
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print("\nplaced %d repair(s), refilled" % added)
    del keep
    print("GND vias now: %d" % sum(
        1 for t in board.GetTracks()
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"))
    board.Save(dst)
    print("saved", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--dry" in sys.argv)

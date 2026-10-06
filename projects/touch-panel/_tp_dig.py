"""Why a net will not route, on the board _tp_try.py would build.

_tp_try.py answers "does this net route"; it does not say what stopped it, and
the CSEL nets fail identically under every GND cut tried -- 68, 127 and 150
segments removed, one layer and both -- so they are not blocked by the corridor
spine and re-running the cut again would only reconfirm that.  This builds the
same scratch board and then reproduces route_net()'s setup for each named net,
printing the pieces that actually decide the outcome:

  * every pad's grid nodes and how many of them sit under `blocked`
  * `reach` -- the slice of the net's own copper that is joined to pad 0, which
    is the mask A* is given as its goal
  * a free-space flood that may change layers, from pad 0 to each other pad

A pad the flood cannot touch is walled in by copper already on the board.  A pad
the flood reaches but A* cannot is a crowding artefact and belongs to rip-up,
not to geometry.

  NETS=CSEL0,CSEL5 CUT_X0=99.8 CUT_X1=102.4 CUT_Y0=105 CUT_Y1=250 python _tp_dig.py

Env: NETS, TAG, and the CUT_* set from _tp_try.py.
"""
import os
import shutil
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                      # noqa: E402

NETS = [n for n in os.environ.get("NETS", "ROW16").split(",") if n]
TAG = os.environ.get("TAG", "dig")
PROBE = os.path.join(HERE, "_tp_dig_%s.kicad_pcb" % TAG)

X0 = float(os.environ.get("CUT_X0", "100.3"))
X1 = float(os.environ.get("CUT_X1", "101.6"))
Y0, Y1 = os.environ.get("CUT_Y0"), os.environ.get("CUT_Y1")
fy0, fy1 = (float(Y0), float(Y1)) if Y0 and Y1 else (0.0, 0.0)
CUT_NET = os.environ.get("CUT_NET", "GND")
CUT_LAYER = os.environ.get("CUT_LAYER", "F")

shutil.copyfile(R.BOARD, PROBE)


def cut_spine():
    board = pcbnew.LoadBoard(PROBE)
    kill = []
    for t in list(board.GetTracks()):
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() != CUT_NET:
            continue
        if CUT_LAYER == "F" and t.GetLayer() != pcbnew.F_Cu:
            continue
        if CUT_LAYER == "B" and t.GetLayer() != pcbnew.B_Cu:
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
        x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        if (X0 <= x1 <= X1 and X0 <= x2 <= X1
                and fy0 <= y1 <= fy1 and fy0 <= y2 <= fy1):
            kill.append(t)
    for t in kill:
        board.Remove(t)
    board.Save(PROBE)
    print("cut %d %s segment(s), layer %s" % (len(kill), CUT_NET, CUT_LAYER))
    return kill


if os.environ.get("NO_GND"):
    # Same board _tp_nognd.py routes: GND's mesh is gone, so nothing here is
    # HEAD's spine.  Lets the wall question be asked of the board the pass
    # actually ran on rather than of the cut approximation.
    _b = pcbnew.LoadBoard(PROBE)
    _all = list(_b.GetTracks())
    _kill = [t for t in _all if t.GetNetname() == CUT_NET]
    for _t in _kill:
        _b.Remove(_t)
    _b.Save(PROBE)
    print("deleted %d %s track(s); %d of %d left"
          % (len(_kill), CUT_NET, len(_all) - len(_kill), len(_all)))

if Y0 is not None and Y1 is not None:
    _keep_alive = cut_spine()

board = pcbnew.LoadBoard(PROBE)
rt = R.Router(board)
R.absorb(board, rt)


def flood(free, seeds):
    """Free space reachable from `seeds`, eight-connected, changing layers where
    a via is allowed.  The same movement graph astar() uses, so "the flood gets
    there" and "A* can get there" mean the same thing.

    `seeds` are (i, j, l) triples -- the order reachable() takes -- which is not
    the order the mask is indexed in, so every lookup has to spell out
    free[l, i, j].  Writing free[(i, j, l)] instead reads as a fancy index down
    the layer axis and blows up on the first i of any size.
    """
    seen = np.zeros_like(free)
    stack = [(i, j, l) for (i, j, l) in seeds if free[l, i, j]]
    for (i, j, l) in stack:
        seen[l, i, j] = True
    while stack:
        i, j, l = stack.pop()
        nb = [(i + di, j + dj, l) for di, dj in
              ((1, 0), (-1, 0), (0, 1), (0, -1),
               (1, 1), (1, -1), (-1, 1), (-1, -1))]
        if rt.via_ok(R.mx(i), R.my(j)):
            nb.append((i, j, 1 - l))
        for (i2, j2, l2) in nb:
            if not (0 <= i2 < R.NX and 0 <= j2 < R.NY):
                continue
            if free[l2, i2, j2] and not seen[l2, i2, j2]:
                seen[l2, i2, j2] = True
                stack.append((i2, j2, l2))
    return seen


for NET in NETS:
    w = R.WIDTHS.get(NET, R.DEFAULT_W)
    hw = w / 2.0
    blocked, via_blocked = rt.blocked_for(NET, hw)
    pads = rt.pads.get(NET, [])
    print("\n=== %s  w=%.2f  %d pad(s)" % (NET, w, len(pads)))
    if len(pads) < 2:
        print("    nothing to route (needs >1 pad)")
        continue

    for k, (x, y, nodes, layers) in enumerate(pads):
        ls = layers or (0, 1)
        nb = sum(blocked[l, i, j] for l in ls for (i, j) in nodes)
        print("  [%2d] (%8.3f,%8.3f) layers=%s nodes=%4d blocked=%4d"
              % (k, x, y, ls, len(nodes) * len(ls), nb))

    # route_net()'s own setup: the net's frozen copper, pad 0 landed on it.
    conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    near = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    nfr = 0
    for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
        if onet == NET:
            nfr += 1
            R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
            R.raster_seg(near, layer, x1, y1, x2, y2, ww / 2.0 + R.GRID / 2.0)
    nvia = 0
    for (vnet, vx, vy) in rt.frozen_vias:
        if vnet == NET:
            nvia += 1
            for layer in (0, 1):
                R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
                R.raster_circle(near, layer, vx, vy, R.VIA_D / 2.0 + R.GRID / 2.0)
    nconn = int(conn.sum())
    if nconn:
        cl, ci, cj = np.where(conn)
        print("  frozen copper spans x %.2f..%.2f  y %.2f..%.2f  layers %s"
              % (R.mx(ci.min()), R.mx(ci.max()), R.my(cj.min()), R.my(cj.max()),
                 sorted(set(cl.tolist()))))
    _, _, n0, l0 = pads[0]
    for l in (l0 or (0, 1)):
        for (i, j) in n0:
            conn[l, i, j] = True

    seed = [(i, j, l) for l in (l0 or (0, 1)) for (i, j) in n0]
    reach = R.reachable(conn, seed, rt.via_ok)
    print("  frozen: %d segment(s), %d via(s);  conn=%d cells, +pad0 -> %d"
          % (nfr, nvia, nconn, int(conn.sum())))
    print("  reach=%d cells (%.1f%% of conn is joined to pad 0); "
          "%d of them under `blocked`"
          % (int(reach.sum()),
             100.0 * reach.sum() / max(1, int(conn.sum())),
             int((reach & blocked).sum())))
    if len(reach.nonzero()[0]):
        # np.where on an (NL, NX, NY) mask yields (layer, i, j) -- so the x span
        # comes from the *second* array and the y span from the third.
        rl, ri, rj = np.where(reach)
        print("     reach spans x %.2f..%.2f  y %.2f..%.2f  layers %s"
              % (R.mx(ri.min()), R.mx(ri.max()), R.my(rj.min()), R.my(rj.max()),
                 sorted(set(rl.tolist()))))

    # The failure itself: the same A* call route_net() makes, with the same
    # goal mask, so a None here is the "cannot reach pad" that shows up in the
    # router's log -- and it isolates that from the rip-up loop around it.
    print("  blocked=%d  edge=%d  of %d cell(s)"
          % (int(blocked.sum()), int(rt.edge.sum()), R.NL * R.NX * R.NY))
    for k in range(1, len(pads)):
        _, _, nodes, layers = pads[k]
        starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
        p = rt.astar(blocked, via_blocked, starts, reach)
        print("     astar -> pad[%2d] (%8.3f,%8.3f)  %d start(s): %s"
              % (k, pads[k][0], pads[k][1], len(starts),
                 "None" if p is None else "%d cell(s)" % len(p)))

    # The flood above may change layers wherever via_ok() says so; astar() uses
    # the precomputed `via_blocked` instead.  If a pad is reachable only by
    # crossing over, those two disagree and the difference is the whole failure.
    print("     via_blocked=%d cell(s)" % int(via_blocked.sum()))
    vbz = np.zeros_like(via_blocked)
    for k in range(1, len(pads)):
        _, _, nodes, layers = pads[k]
        starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
        p = rt.astar(blocked, vbz, starts, reach)
        print("     astar(no via ban) -> pad[%2d]: %s"
              % (k, "None" if p is None else "%d cell(s)" % len(p)))

    # Is each pad joinable at all, ignoring the net's own copper as an obstacle?
    free = ~blocked & ~rt.edge
    fl = flood(free, seed)
    print("  free space from pad 0: %d cells of %d board-wide"
          % (int(fl.sum()), int(free.sum())))
    # Same flood, but pinned to one side.  If pad 0 can only ever leave its own
    # copper by crossing over, the pad is reachable in the two-layer graph and
    # unreachable in the one-layer graph astar() actually searches whenever the
    # via gate disagrees.
    for lay, tag in ((0, "F"), (1, "B")):
        f1 = free.copy()
        f1[1 - lay] = False
        print("     %s-only  flood from pad 0: %d cells"
              % (tag, int(flood(f1, seed).sum())))
    for k, (x, y, nodes, layers) in enumerate(pads):
        ls = layers or (0, 1)
        touch = any(fl[l, i, j] for l in ls for (i, j) in nodes)
        onreach = any(reach[l, i, j] for l in ls for (i, j) in nodes)
        print("     pad[%2d] (%8.3f,%8.3f)  flood-reaches=%-5s  on-reach=%-5s"
              % (k, x, y, touch, onreach))

os.remove(PROBE)

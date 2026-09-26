"""Flood the reachable pocket around J1 pad 4 / pad 6 and name the walls."""
import sys, os, types, collections
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1'][0]
src = {"ROW3": j1.FindPadByNumber("4"), "ROW5": j1.FindPadByNumber("6")}
exempt = {p.m_Uuid.AsString() for p in src.values()}
items = list(board.GetTracks())
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.m_Uuid.AsString() not in exempt:
            items.append(p)
nm = np.array([it.GetNetname() for it in items], dtype=object)

safety = 0.0
keep = 0.2 + 0.1 + safety; pad_keep = 0.2 + 0.3 + safety
egk = edge_clear + 0.2 + safety; vek = egk + 0.3
grid = E.NGrid(board, 0.1, keep, egk, pad_keep, vek, layers)
grid.build(items)
own_net = {}
for lay in layers:
    o = grid.OWN[lay]
    own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")

li = {l: k for k, l in enumerate(layers)}
NB = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))

for name in ("ROW3", "ROW5"):
    OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
          for lay in layers}
    VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                      & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
    p = src[name]
    c = p.GetPosition(); ci, cj = grid.ij(c.x/S, c.y/S)
    seen = set(); q = collections.deque()
    for lay in layers:
        if OK[lay][cj, ci]:
            seen.add((li[lay], ci, cj)); q.append((li[lay], ci, cj))
    if not q:
        # seed must be forced: find the legal cell nearest the pad centre
        best = None
        for lay in layers:
            for dj in range(-8, 9):
                for di in range(-8, 9):
                    i2, j2 = ci+di, cj+dj
                    if 0 <= i2 < grid.nx and 0 <= j2 < grid.ny and OK[lay][j2, i2]:
                        d = di*di+dj*dj
                        if best is None or d < best[0]: best = (d, lay, i2, j2)
        if best:
            seen.add((li[best[1]], best[2], best[3])); q.append((li[best[1]], best[2], best[3]))
    wall = collections.Counter()
    bbox = {l: [1e9,1e9,-1e9,-1e9] for l in layers}
    while q:
        k = q.popleft(); l, i, j = k; lay = layers[l]
        x, y = grid.xy(i, j)
        bb = bbox[lay]
        bb[0]=min(bb[0],x); bb[1]=min(bb[1],y); bb[2]=max(bb[2],x); bb[3]=max(bb[3],y)
        for di, dj in NB:
            ni, nj = i+di, j+dj
            if not (0 <= ni < grid.nx and 0 <= nj < grid.ny): continue
            if di and dj and not (OK[lay][j, ni] and OK[lay][nj, i]):
                for (qi, qj) in ((ni, j), (i, nj)):
                    o = grid.OWN[lay][qj, qi]
                    if o >= 0: wall[int(o)] += 1
                continue
            if OK[lay][nj, ni]:
                nk = (l, ni, nj)
                if nk not in seen: seen.add(nk); q.append(nk)
            else:
                o = grid.OWN[lay][nj, ni]
                if o >= 0: wall[int(o)] += 1
        if VOK[j, i]:
            for ol in layers:
                if ol == lay: continue
                m = li[ol]
                if OK[ol][j, i]:
                    nk = (m, i, j)
                    if nk not in seen: seen.add(nk); q.append(nk)
    print("=== %s : pad %s @ (%.3f,%.3f) ===" % (name, p.GetNumber(), c.x/S, c.y/S))
    print("  reachable pocket: %d cell(s)  (%.1f mm^2)" % (len(seen), len(seen)*0.01))
    for lay in layers:
        bb = bbox[lay]
        if bb[2] > bb[0]:
            print("    %-5s x %8.3f..%8.3f   y %8.3f..%8.3f"
                  % (board.GetLayerName(lay), bb[0], bb[2], bb[1], bb[3]))
    print("  WALLS (items whose copper bounds the pocket), top 14 by contact:")
    for o, n in wall.most_common(14):
        it = items[o]; sh = probe.item_shape(it)
        if isinstance(it, pcbnew.PCB_TRACK):
            s, e = it.GetStart(), it.GetEnd()
            g = "%s (%.3f,%.3f)->(%.3f,%.3f) w=%.2f" % (
                board.GetLayerName(it.GetLayer()), s.x/S, s.y/S, e.x/S, e.y/S, it.GetWidth()/S)
        else:
            bb = it.GetBoundingBox()
            g = "pad %s  x %.3f..%.3f y %.3f..%.3f" % (
                getattr(it, 'GetNumber', lambda: '?')() if isinstance(it, pcbnew.PAD) else '?',
                bb.GetLeft()/S, bb.GetRight()/S, bb.GetTop()/S, bb.GetBottom()/S)
        print("    %-6s x%-5d  %s" % (it.GetNetname(), n, g))
    print(flush=True)

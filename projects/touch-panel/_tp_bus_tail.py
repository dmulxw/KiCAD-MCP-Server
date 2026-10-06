def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", default=None)
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--safety", type=float, default=0.1)
    ap.add_argument("--via-cost", type=float, default=25.0)
    ap.add_argument("--lock", action="store_true",
                    help="lock emitted copper so an autorouter routes around "
                         "it (Specctra (type fix)) instead of ripping it up")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--conflict", action="store_true")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    keep = a.clearance + TRACK_W / 2 + a.safety
    pad_keep = a.clearance + VIA_DIA / 2 + a.safety
    edge_keep = edge_clear + TRACK_W / 2 + a.safety
    via_edge_keep = edge_clear + VIA_DIA / 2 + a.safety
    print("edge clearance rule: %.3f mm   keep %.2f  pad_keep %.2f"
          % (edge_clear, keep, pad_keep))

    only = set(a.nets) if a.nets else None
    ntr = nvi = nfail = 0

    for (name, ends) in END:
        if only and name not in only:
            continue
        print("=" * 72)
        pads = []
        for (ref, num) in ends:
            p = start_pad(board, ref, num)
            if p is None:
                print("%s: %s pad %s NOT FOUND" % (name, ref, num))
            pads.append(p)
        print("%s: %d endpoint(s), routing as a chain"
              % (name, len([p for p in pads if p is not None])))

        # Each link goes from the next endpoint to the copper already laid.
        # Goals are restricted to what has been routed so far, so the chain
        # cannot jump ahead and connect U3 before U2.
        for idx in range(1, len(pads)):
            start = pads[idx]
            if start is None:
                continue
            pending = {p.m_Uuid.AsString() for p in pads[idx + 1:] if p is not None}
            own = [it for it in net_items(board, name)
                   if not (isinstance(it, pcbnew.PAD)
                           and it.m_Uuid.AsString() in pending)]
            others = [it for it in board.GetTracks() if it.GetNetname() != name]
            for fp in board.GetFootprints():
                others.extend(p for p in fp.Pads() if p.GetNetname() != name)

            pp0 = start.GetPosition()
            grid = Grid(board, a.step, keep, edge_keep, pad_keep,
                        via_edge_keep, align=(pp0.x / S, pp0.y / S))
            grid.build(layers, others)

            pp = start.GetPosition()
            pc = (pp.x / S, pp.y / S)
            si, sj = grid.ij(*pc)
            r = start.GetBoundingBox()
            start_cells = []
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    i, j = si + di, sj + dj
                    if 0 <= i < grid.nx and 0 <= j < grid.ny:
                        x, y = grid.xy(i, j)
                        if (r.GetLeft() / S <= x <= r.GetRight() / S
                                and r.GetTop() / S <= y <= r.GetBottom() / S):
                            start_cells.append((pcbnew.F_Cu, i, j))
            if not start_cells:
                start_cells = [(pcbnew.F_Cu, si, sj)]

            goals = set()
            pad_uuid = start.m_Uuid.AsString()
            for it in own:
                if isinstance(it, pcbnew.PAD) and it.m_Uuid.AsString() == pad_uuid:
                    continue
                shape = item_shape(it)
                if shape is None:
                    continue
                cx, cy = (shape[0] + shape[2]) / 2, (shape[1] + shape[3]) / 2
                for l in [l for l in layers if on_layer(it, l)]:
                    i, j = grid.ij(cx, cy)
                    if 0 <= i < grid.nx and 0 <= j < grid.ny:
                        goals.add((l, i, j))

            tag = "%s[%d] %s->%s" % (name, idx, ends[idx][0] + "." + ends[idx][1],
                                     ends[0][0] + "." + ends[0][1])
            if not goals:
                print("  %-22s no goals (nothing to connect to)" % tag)
                nfail += 1
                continue

            path = astar_dual(grid, layers, start_cells, goals, a.via_cost,
                              conflict=a.conflict)
            if path is None:
                print("  %-22s NO PATH   (%d goal cell(s))" % (tag, len(goals)))
                nfail += 1
                continue

            runs = layer_runs(path)
            tracks = []
            for run in runs:
                tracks.extend(merge_run(run))
            vias = []
            for k in range(1, len(runs)):
                c = runs[k][0]
                x, y = grid.xy(c[1], c[2])
                if any((x - vx) ** 2 + (y - vy) ** 2 < VIA_DIA ** 2
                       for vx, vy in vias):
                    continue
                vias.append((x, y))

            length = 0.0
            for k in range(1, len(path)):
                if path[k][0] == path[k - 1][0]:
                    dx = path[k][1] - path[k - 1][1]
                    dy = path[k][2] - path[k - 1][2]
                    length += (dx * dx + dy * dy) ** 0.5 * a.step

            if a.conflict:
                blockers = {}
                for layer, i, j in path:
                    d, who = grid.cell(layer, i, j)
                    if who >= 0 and d < keep:
                        blockers.setdefault(who, [0, d])
                        blockers[who][0] += 1
                        blockers[who][1] = min(blockers[who][1], d)
                print("  %-22s %5.1fmm %2d via(s)  crosses %d other-net item(s)"
                      % (tag, length, len(vias), len(blockers)))
                for who, (cells, worst) in sorted(blockers.items(),
                                                  key=lambda kv: -kv[1][0])[:5]:
                    it = others[who]
                    print("        %4d cell(s) worst %+.3fmm  net %s"
                          % (cells, worst, it.GetNetname()))
                continue

            netinfo = board.FindNet(name)
            for x, y in vias:
                if not a.dry_run:
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I(int(x * S), int(y * S)))
                    v.SetWidth(int(VIA_DIA * S))
                    v.SetDrill(int(0.3 * S))
                    v.SetNet(netinfo)
                    v.SetLocked(a.lock)
                    board.Add(v)
            for layer, i0, j0, i1, j1 in tracks:
                if i0 == i1 and j0 == j1:
                    continue
                x0, y0 = grid.xy(i0, j0)
                x1, y1 = grid.xy(i1, j1)
                if not a.dry_run:
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(pcbnew.VECTOR2I(int(x0 * S), int(y0 * S)))
                    t.SetEnd(pcbnew.VECTOR2I(int(x1 * S), int(y1 * S)))
                    t.SetWidth(int(TRACK_W * S))
                    t.SetLayer(layer)
                    t.SetNet(netinfo)
                    t.SetLocked(a.lock)
                    board.Add(t)
            ntr += len(tracks)
            nvi += len(vias)
            print("  %-22s %6.1fmm  %2d track(s)  %2d via(s)"
                  % (tag, length, len(tracks), len(vias)))

    print("=" * 72)
    print("TOTAL: %d track(s), %d via(s), %d link(s) with no path"
          % (ntr, nvi, nfail))
    if not a.dry_run:
        board.BuildConnectivity()
        pcbnew.SaveBoard(a.board, board)
        print("saved %s" % a.board)


if __name__ == "__main__":
    main()

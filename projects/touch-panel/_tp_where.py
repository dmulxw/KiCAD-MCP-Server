"""Where are the pads of the nets that fail, and are they sitting under copper?"""
import sys
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

for ref in ("U1", "U2", "U3", "U4"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        print("%s: MISSING" % ref)
        continue
    p = fp.GetPosition()
    print("\n%s @ (%.2f, %.2f) rot=%s layer=%s"
          % (ref, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
             fp.GetOrientationDegrees(), board.GetLayerName(fp.GetLayer())))
    pads = sorted(fp.Pads(), key=lambda q: int(q.GetNumber()))
    for q in pads:
        pos = q.GetPosition()
        print("   %-3s (%8.3f,%8.3f)  %s"
              % (q.GetNumber(), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                 q.GetNetname()))

print("\n--- nets that fail, and every pad they own ---")
for net in ("ROW16", "ROW2", "CSEL1", "IO9", "+3V3"):
    pads = rt.pads.get(net)
    if not pads:
        print("\n%s: no pads" % net)
        continue
    w = R.WIDTHS.get(net, R.DEFAULT_W)
    blocked, _ = rt.blocked_for(net, w / 2.0)
    print("\n%s  w=%.2f  %d pad(s)" % (net, w, len(pads)))
    for k, (x, y, nodes, layers) in enumerate(pads):
        ls = layers or (0, 1)
        nb = sum(blocked[l, i, j] for l in ls for (i, j) in nodes)
        tot = len(nodes) * len(ls)
        flag = "  <-- BURIED" if nb == tot and tot else ""
        print("   [%2d] (%8.3f,%8.3f) L%s %4d/%4d blocked%s"
              % (k, x, y, ls, nb, tot, flag))

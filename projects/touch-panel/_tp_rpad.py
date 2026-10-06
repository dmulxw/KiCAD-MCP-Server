"""Why can no trace land on R pad 1?  Measure the pocket it sits in.

The 26 stranded nets all fail at the same shape of place -- "cannot reach pad
(101.59, y)" and "cannot reach pad (105.76, y)" -- so the wall is not the story;
something local is.  This prints the two things that would box a pad in: the gap
to the pad next to it, and the copper sitting just west of it.

  python _tp_rpad.py
"""
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)

print("=== the R column: pad 1 (signal) and pad 2 (GND), and the gap between ===")
rows = []
for f in board.GetFootprints():
    ps = {str(p.GetNumber()): p for p in f.Pads()}
    if "1" not in ps or "2" not in ps:
        continue
    p1, p2 = ps["1"], ps["2"]
    a, b = p1.GetBoundingBox(), p2.GetBoundingBox()
    x1, y1 = TO(a.GetRight()), TO(a.GetTop())
    x2 = TO(b.GetLeft())
    rows.append((TO(f.GetPosition().y), f.GetReference(),
                 TO(p1.GetPosition().x), TO(p1.GetPosition().y), p1.GetNetname(),
                 TO(p2.GetPosition().x), p2.GetNetname(),
                 TO(a.GetWidth()), TO(a.GetHeight()), x2 - x1,
                 [board.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)
                  if p1.IsOnLayer(l)]))
for (_, ref, x1, y1, n1, x2, n2, w, h, gap, lays) in sorted(rows):
    print("  %-4s pad1 (%7.3f,%7.3f) %-8s %.2fx%.2f  pad2 x=%7.3f %-4s"
          "  gap %.3f mm  layers=%s"
          % (ref, x1, y1, n1, w, h, x2, n2, gap, ",".join(lays)))

print("\n=== F.Cu GND copper in x 99.0..103.5 (the spine beside them) ===")
seg, ext = 0, []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        x, y = TO(p.x), TO(p.y)
        if t.GetNetname() == "GND" and 99.0 <= x <= 103.5:
            ext.append(("via", x, y, y, TO(t.GetWidth(pcbnew.F_Cu))))
        continue
    if t.GetLayer() != pcbnew.F_Cu or t.GetNetname() != "GND":
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if max(x1, x2) < 99.0 or min(x1, x2) > 103.5:
        continue
    seg += 1
    ext.append(("seg", min(x1, x2), min(y1, y2), max(y1, y2), TO(t.GetWidth())))
print("  %d segment(s):" % seg)
for (k, x, y0, y1, w) in sorted(ext, key=lambda r: r[2])[:60]:
    if k == "via":
        print("    via  x=%7.3f  y=%7.3f            w=%.2f" % (x, y0, w))
    else:
        print("    seg  x=%7.3f  y %7.3f..%7.3f  w=%.2f" % (x, y0, y1, w))

lo = min(r[2] for r in ext) if ext else 0
hi = max(r[3] for r in ext) if ext else 0
print("  spine spans y %.2f..%.2f" % (lo, hi))

print("\n=== free cells beside each R pad 1, on both layers (4 mm box) ===")
sys.path.insert(0, ".")
import _tp_route as R  # noqa: E402

router = R.Router(board)
blk, vblk = router.blocked_for("__nothing__", 0.15)
for (_, ref, x1, y1, n1, x2, n2, w, h, gap, _l) in sorted(rows)[:6]:
    i, j = R.gi(x1), R.gj(y1)
    row = []
    for dx in range(-10, 11):
        c = []
        for l, nm in ((0, "F"), (1, "B")):
            c.append(nm if not blk[l, i + dx, j] else ".")
        row.append("%.1f%s%s" % (R.mx(i + dx), c[0], c[1]))
    print("  %-4s y=%.1f  %s" % (ref, y1, " ".join(row)))
print("  (x, then F/B: letter = that layer free at the row's own y)")

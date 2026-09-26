"""Is the left gutter sealed, or just narrow?  Dump the raw OK mask.

A 1x20 header cannot feed a trunk through a wall, so the answer decides the
whole interface question.  No astar, no goal sets -- just the mask.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

S = 1e6
TRACK_W = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

board = pcbnew.LoadBoard('_final.kicad_pcb')
GRAVE = []
E.place(board, "J1B", E.HDR_LIB, E.HDR_FP, E.RIGHT_X, E.RIGHT_Y, {})

edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                  for p in fp.Pads()]
g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
g.build(allc)
print("origin %s  grid %dx%d" % (g.xy(0, 0), g.nx, g.ny), flush=True)

# x from 99.00 to 103.00, F.Cu and B.Cu, at a few heights in the left gutter.
I0 = int(round((99.00 - 89.45) / step))
I1 = int(round((103.00 - 89.45) / step))
print("\nx %.2f .. %.2f   '#'=blocked  '.'=free   left gutter" % (99.00, 103.00))
print("        " + "".join(str((99 + k // 10) % 10) if k % 10 == 0 else " "
                           for k in range(41)))
for y in (120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0,
          200.0, 203.75, 210.0, 220.0, 230.0, 240.0):
    j = int(round((y - 99.45) / step))
    if not (0 <= j < g.ny):
        continue
    f = "".join("#" if not g.OK[LAYERS[0]][j, i] else "." for i in range(I0, I1 + 1))
    b = "".join("#" if not g.OK[LAYERS[1]][j, i] else "." for i in range(I0, I1 + 1))
    print("  y=%6.2f F %s" % (y, f))
    print("           B %s" % b)

# longest free horizontal run per layer, per row -- the real capacity number
print("\nlongest free run in x within the gutter (99..103), per 2mm of y:")
print("   y      F.Cu   B.Cu")
for yy in range(118, 243, 2):
    j = int(round((yy - 99.45) / step))
    if not (0 <= j < g.ny):
        continue
    out = []
    for l in (0, 1):
        best = cur = 0
        for i in range(I0, I1 + 1):
            cur = cur + 1 if g.OK[LAYERS[l]][j, i] else 0
            best = max(best, cur)
        out.append(best * step)
    print("  %5.1f  %5.2f  %5.2f" % (yy, out[0], out[1]), flush=True)

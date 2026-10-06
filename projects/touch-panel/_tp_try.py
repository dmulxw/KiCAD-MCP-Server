"""Try one routing configuration against a scratch copy of the panel.

_tp_cut.py proved the corridor GND spine is the wall: cutting 68 of its F.Cu
segments let ROW16 through alone.  On the full 40-net pass the same cut lifts
the board from 12 routed nets to 23 -- so the wall is real, but it is not the
only thing holding the remaining 17 back.  This runs an arbitrary configuration
on a scratch board so a failure can be attributed to geometry ("walled in even
with the board to itself") or to congestion ("routes alone, loses the race")
without ever touching touch-panel.kicad_pcb.

  TAG=row17 ONLY_SET="ROW17 ROW18 ROW20" CUT_Y0=140 CUT_Y1=246 python _tp_try.py

Env (ONLY_SET/ORDER/ROUNDS are consumed by _tp_route, so ONLY_SET must be set
before this script imports it):
  ONLY_SET        nets allowed to gain copper; default is _tp_route's own list
  ORDER           span | long | none | lane | lane-rev
  ROUNDS          rip-up rounds
  CUT_X0/CUT_X1   x band of the spine to delete   (default 100.3 .. 101.6)
  CUT_Y0/CUT_Y1   y band; both must be set for a cut to happen
  TAG             scratch-file suffix, so runs can proceed in parallel
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                      # noqa: E402

TAG = os.environ.get("TAG", "try")
PROBE = os.path.join(HERE, "_tp_try_%s.kicad_pcb" % TAG)

X0 = float(os.environ.get("CUT_X0", "100.3"))
X1 = float(os.environ.get("CUT_X1", "101.6"))
Y0, Y1 = os.environ.get("CUT_Y0"), os.environ.get("CUT_Y1")
fy0, fy1 = (float(Y0), float(Y1)) if Y0 and Y1 else (0.0, 0.0)

CUT_NET = os.environ.get("CUT_NET", "GND")
CUT_LAYER = os.environ.get("CUT_LAYER", "F")          # F | B | A (both)

shutil.copyfile(R.BOARD, PROBE)


def cut_spine():
    """Delete the GND F.Cu run that walls the corridor off from the matrix.

    Only whole segments inside the band go, so a stub reaching out to a pad is
    left alone and nothing outside the corridor is touched.  The proxies stay
    referenced until the board is saved: letting them die here corrupts SWIG's
    object table before Remove() has been flushed.
    """
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
            kill.append((t, y1, y2))
    for (t, _, _) in kill:
        board.Remove(t)
    ys = sorted(set(round(a, 2) for (_, a, b) in kill)
                | set(round(b, 2) for (_, a, b) in kill))
    print("cut %d GND F.Cu segment(s) in x %.2f..%.2f y %.0f..%.0f%s"
          % (len(kill), X0, X1, fy0, fy1,
             "   y spans %.2f .. %.2f" % (ys[0], ys[-1]) if ys else ""))
    board.Save(PROBE)
    return kill


if Y0 is not None and Y1 is not None:
    _keep_alive = cut_spine()

R.BOARD = PROBE
try:
    R.main()
except SystemExit as exc:
    print("router exited %s" % (exc.code,))
finally:
    if os.path.exists(PROBE):
        os.remove(PROBE)

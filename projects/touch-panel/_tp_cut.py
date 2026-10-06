"""Does the corridor GND spine actually seal the 595 outputs?

_tp_line.py shows the only F.Cu obstacle between the chip pads and the row
resistors is one 0.2 mm GND trace at x~100.85, and that B.Cu is solid across the
whole band, so that trace is the entire barrier.  GND is the most flexible net
on the board -- 86 pads, no length constraint -- so the question is whether
removing it unseals the outputs.  This cuts it on a scratch copy, reruns the
router and leaves the real board alone either way.

  CUT_Y0=140 CUT_Y1=246 ONLY_SET=ROW16 python _tp_cut.py
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

X0, X1 = 100.3, 101.6
Y0 = float(os.environ.get("CUT_Y0", "140"))
Y1 = float(os.environ.get("CUT_Y1", "246"))

PROBE = HERE + r"\_tp_cut.kicad_pcb"
shutil.copyfile(R.BOARD, PROBE)

board = pcbnew.LoadBoard(PROBE)

kill = []
for t in list(board.GetTracks()):
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetNetname() != "GND" or t.GetLayer() != pcbnew.F_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    if (X0 <= x1 <= X1 and X0 <= x2 <= X1 and Y0 <= y1 <= Y1 and Y0 <= y2 <= Y1):
        kill.append((t, x1, y1, x2, y2))

for (t, *_) in kill:
    board.Remove(t)
_keep_alive = kill                                       # SWIG: proxies must live

print("cut %d GND F.Cu segment(s) in x %.1f..%.1f, y %.0f..%.0f"
      % (len(kill), X0, X1, Y0, Y1))
ys = sorted(set(round(k[2], 2) for k in kill) | set(round(k[4], 2) for k in kill))
if ys:
    print("   y spans %.2f .. %.2f" % (ys[0], ys[-1]))
board.Save(PROBE)
del board

R.BOARD = PROBE
try:
    R.main()
except SystemExit as exc:
    print("router exited %s" % (exc.code,))

os.remove(PROBE)

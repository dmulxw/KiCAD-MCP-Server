"""Run the panel router against a scratch copy of the board, for one net.

Answers the question the pre-flight raises but cannot settle: route_net()
computes `taken` once, before its loop, and the 595 pad sorts first, so on a
net whose old copper is a separate island *every* old pad looks stranded.  If
it then lays one trace per old pad the corridor is wasted and the output is
hundreds of duplicates; if the loop's conn growth makes later pads no-ops, it
lays one.  Count, don't reason.

  ONLY_SET=ROW0 python _tp_one.py
"""
import os
import shutil
import sys

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402
import _tp_route as R                                  # noqa: E402

PROBE = HERE + r"\_tp_probe.kicad_pcb"
shutil.copyfile(R.BOARD, PROBE)

before = len(list(pcbnew.LoadBoard(PROBE).GetTracks()))
R.BOARD = PROBE
R.main()
after = len(list(pcbnew.LoadBoard(PROBE).GetTracks()))
print("\nscratch board tracks %d -> %d" % (before, after))
os.remove(PROBE)

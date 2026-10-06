"""Run _tp_route.py's router against a scratch board instead of the real panel.

Opening the west wall is a trial: the three B.Cu trunks are lifted on a copy, the
router is asked to cross 39 nets under the freed band, and only if that comes
back clean does the same edit get applied to touch-panel.kicad_pcb.  main() reads
the module-level BOARD at call time, so rebinding it here is enough -- no fork of
the 1150-line router, and nothing in it can drift out of sync.

  BOARD_OVERRIDE=... python _tp_route_wall.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _tp_route as R

R.BOARD = os.environ.get(
    "BOARD_OVERRIDE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tp_wall.kicad_pcb"))

print("router aimed at", R.BOARD)
R.main()

"""How many net fragments are left unjoined, per KiCad's own connectivity engine.

RIPPABLE hands the router the board's existing copper and lets rip() lift any of
it.  route_all() only scores the nets in `todo`, so a pass that gained one of
those by ripping, say, COL7 and failing to put it back would report success while
silently cutting a net that has nothing to do with the task.  The score cannot
see that, and neither can the [OK ]/[FAIL] lines.

KiCad's CONNECTIVITY_DATA can.  BuildConnectivity() unions pads, tracks and vias
exactly as DRC does, and GetUnconnectedCount() is how many nets are still in more
than one piece.  Comparing that number before and after a pass is the check the
router's own bookkeeping cannot fake.

GetUnconnectedCount takes a visible-only flag; False counts every layer, which is
what a two-layer board wants.

  python _tp_netparts.py                                # the real board, as-is
  python _tp_netparts.py scratch/_tp_rip_rip1.kicad_pcb # any board
"""
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")

path = sys.argv[1] if len(sys.argv) > 1 else BOARD
board = pcbnew.LoadBoard(path)
board.BuildConnectivity()
conn = board.GetConnectivity()

tracks = list(board.GetTracks())
vias = [t for t in tracks if isinstance(t, pcbnew.PCB_VIA)]

print("%s" % path)
print("  footprints   %d" % len(list(board.GetFootprints())))
print("  tracks/vias  %d  (%d via)" % (len(tracks), len(vias)))
print("  nets         %d" % conn.GetNetCount())
print("  UNCONNECTED  %d" % conn.GetUnconnectedCount(False))

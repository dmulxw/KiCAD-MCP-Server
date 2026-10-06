"""How far does the panel get with GND's track mesh gone?

_tp_zone.py showed GND is only 297 of 2,410 segments and 2 of 529 vias -- yet
deleting it flips CSEL0 from None to routed and ROW17 from nothing to all eleven
pads.  It is not the *amount* of copper that matters (via_blocked falls only
389,611 <- 394,110, 1.1%) but *where*.  Those few thousand cells sit exactly on
the corridor's escape paths.

That makes deleting the mesh -- and letting a zone carry GND instead -- the
architectural fix, matching the carrier's route-then-pour order: absorb() reads
only GetTracks(), so a pour is invisible to the router and cannot block it.
Before any of that touches the real board, this measures the ceiling: delete
every GND track, drop GND from the pass entirely, and route the other 39 nets.

  python _tp_nognd.py            # all 39 signal nets, ROUNDS=8

Env: ROUNDS, ORDER, TAG, and ONLY_SET to narrow the pass further.
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                      # noqa: E402

TAG = os.environ.get("TAG", "nognd")
PROBE = os.path.join(HERE, "_tp_nognd_%s.kicad_pcb" % TAG)

shutil.copyfile(R.BOARD, PROBE)

board = pcbnew.LoadBoard(PROBE)
all_tracks = list(board.GetTracks())
kill = [t for t in all_tracks if t.GetNetname() == "GND"]
for t in kill:
    board.Remove(t)
board.Save(PROBE)
print("deleted %d GND track(s); %d of %d left"
      % (len(kill), len(all_tracks) - len(kill), len(all_tracks)))
sys.stdout.flush()

R.BOARD = PROBE
try:
    R.main()
except SystemExit as exc:
    print("router exited %s" % (exc.code,))
finally:
    if os.path.exists(PROBE):
        os.remove(PROBE)

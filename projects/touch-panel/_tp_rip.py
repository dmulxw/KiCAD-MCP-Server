"""The full 40-net pass with the board's own copper rippable.

_tp_nognd.py measured the ceiling at 26/39 by deleting GND's mesh, which is the
architecturally clean fix but changes the grounding of a touch-sensing panel and
is not mine to make.  This measures the same pass with nothing deleted and one
variable changed: absorb() files the board's copper as `tracks`/`vias` instead of
`frozen`, so rip() and blocking_nets() can see it.

Why that should be the whole difference.  Every net still failing after the GND
cut has blocked=0 at every pad -- its pads are not under copper -- and its A*
returns None with the via gate on but a 237-to-464-cell path with the gate
zeroed.  via_blocked gates only layer *changes*, so that pair says: no route
exists on either side alone, a via is mandatory, and every legal via site along
the way is occupied.  A via needs VIA_D/2 + clearance = 0.50 mm against the
router's 0.46, so the mask is already more permissive than the rule and nothing
can be loosened.  The copper on top of those sites has to move, and frozen copper
is by construction never a rip-up victim.

Runs on a scratch copy; the real board is never opened for writing.

  RIPPABLE=1 python _tp_rip.py                  # the comparison run
  RIPPABLE=1 ROUNDS=12 python _tp_rip.py        # more repair rounds if it is close
  python _tp_rip.py                             # control: RIPPABLE off, must match 23/40

The [OK ]/[FAIL] lines are not the verdict.  They report what route_net()
returned, which is "this net's pads all sit on copper the tree reached" -- not
"this net is one piece on the finished board".  The verdict is DRC:

  kicad-cli pcb drc --format json --output _drc_<tag>.json --severity-all BOARD
  python _tp_drcsum.py _drc_<tag>.json _drc_base.json

so KEEP=1 leaves the routed board behind for exactly that.  Without it the
scratch file is deleted and the run leaves nothing to check.

Env: RIPPABLE, ROUNDS, ORDER, BLOCK_LIMIT, ONLY_SET, TAG, KEEP, and anything the
router itself reads -- all are read at import, so they have to be set before the
import below, not passed to main().
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)

TAG = os.environ.get("TAG", "rip")
PROBE = os.path.join(HERE, "_tp_rip_%s.kicad_pcb" % TAG)

# The router's own board path has to be read before main() is called, and the
# module reads RIPPABLE/ROUNDS/ONLY_SET at import -- so set the scratch path on
# the module, not the environment, and let the environment carry the rest.
import _tp_route as R                                      # noqa: E402

print("incremental=%s rippable=%s rounds=%d order=%s only=%d net(s)"
      % (R.INCREMENTAL, R.RIPPABLE, R.ROUNDS,
         os.environ.get("ORDER", "span"), len(R.ONLY)))

shutil.copyfile(R.BOARD, PROBE)
R.BOARD = PROBE

before = None
try:
    _b = pcbnew.LoadBoard(PROBE)
    before = len(list(_b.GetTracks()))
    print("scratch board has %d track(s)/via(s) and %d footprint(s)"
          % (before, len(list(_b.GetFootprints()))))
    sys.stdout.flush()

    R.main()
except SystemExit as exc:
    print("router exited %s" % (exc.code,))
finally:
    if os.path.exists(PROBE):
        _a = pcbnew.LoadBoard(PROBE)
        after = len(list(_a.GetTracks()))
        print("tracks/vias: %s -> %d" % (before, after))
        if after < before:
            print("WARNING: the pass lost copper -- %d item(s) unaccounted for"
                  % (before - after))
        if os.environ.get("KEEP"):
            print("kept %s -- now DRC it:\n"
                  "  kicad-cli pcb drc --format json --output _drc_%s.json "
                  "--severity-all \"%s\"\n"
                  "  python _tp_drcsum.py _drc_%s.json _drc_base.json"
                  % (PROBE, TAG, PROBE, TAG))
        else:
            os.remove(PROBE)

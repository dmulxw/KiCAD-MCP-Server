"""Delete one net's copper from the carrier, leaving its pads alone.

route.py's INCREMENTAL mode loads every track already on the board into
`frozen`, and blocked_for() treats frozen copper of *any other* net as an
obstacle even when that net is itself listed in ONLY.  So a net whose copper
seals a pocket cannot be made to yield it by re-routing -- the old copy stays
put.  _probe_open.py measured exactly that: dropping IO12's copper opens R7.1's
pocket from 2665 cells to the whole board.

This is the manual form of that subtraction: strip the named net's copper from
the file so the next route pass sees the space as free.  Pads and footprints
are untouched -- the net still has all its pins, just no wiring.

  python _car_ripnet.py IO12
  python _car_ripnet.py IO12 --dry
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry" in sys.argv
if not args:
    sys.exit(__doc__)

board = pcbnew.LoadBoard(BOARD)

dead = []
for t in board.GetTracks():
    if t.GetNetname() in args:
        # never take copper a footprint owns (U1's thermal vias read as GND)
        par = t.GetParent()
        if par is not None and par.GetClass() == "FOOTPRINT":
            continue
        dead.append(t)

by_net = {}
for t in dead:
    by_net.setdefault(t.GetNetname(), []).append(t)
print("copper to remove:")
for n in sorted(by_net):
    ts = by_net[n]
    mm = sum(pcbnew.ToMM(t.GetLength()) for t in ts
             if not isinstance(t, pcbnew.PCB_VIA))
    print("   %-8s %3d item(s)  %.1f mm"
          % (n, len(ts), sum(pcbnew.ToMM(t.GetLength()) for t in ts
                             if t.GetClass() != "PCB_VIA")))
if not dead:
    print("   (nothing)")
    sys.exit(0)

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

backup = BOARD + ".pre-ripnet.bak"
shutil.copyfile(BOARD, backup)
print("\nbackup -> %s" % backup)

# SWIG: keep every removed proxy alive until the save completes, or the object
# table is corrupted mid-write.
_keep_alive = []
for t in dead:
    board.Remove(t)
    _keep_alive.append(t)

board.Save(BOARD)
after = pcbnew.LoadBoard(BOARD)
print("saved: %d track/via item(s), %d net(s)"
      % (len(list(after.GetTracks())), after.GetNetCount()))
for n in args:
    c = sum(1 for t in after.GetTracks() if t.GetNetname() == n)
    print("   %-8s now %d item(s)" % (n, c))

"""Strip the pour so route.py can run against bare copper.

Memory (carrier-route-pour-order) is explicit that the carrier's order is
route-then-pour, and the reason bites here: absorb() reads GetTracks(), so every
GND stitching via the last pour left behind is read into router.frozen_vias and
treated as an obstacle.  Those vias exist to serve copper that is about to be
torn up and re-laid, so they are the wrong obstacles -- and pour.py deletes and
re-places all of them anyway (its own docstring: "it deletes every zone on the
board first", and every GND via on this board is ours, because route.py skips
the net entirely).

Zones themselves the router cannot see at all -- it never consults them -- but
leaving stale fills on disk while the tracks underneath change would make the
DRC run between the two passes meaningless, so they go too.

This is pour.py's drop_zones() + drop_stitch_vias(), without its main() tail
(which runs at import).  Proxies are kept alive to the save for the usual SWIG
reason.

  python _car_unpour.py --dry
  python _car_unpour.py
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb.pre-unpour.bak")

DRY = "--dry" in sys.argv

board = pcbnew.LoadBoard(BOARD)

zones = list(board.Zones())
vias = [t for t in board.GetTracks()
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]

print("board: %d zone(s), %d GND stitch via(s)"
      % (len(zones), len(vias)))
for z in zones:
    print("   zone net=%-8s layers=%s"
          % (z.GetNetname() or "(none)",
             [pcbnew.LayerName(l) for l in z.GetLayerSet().Seq()]))

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

_keep_alive = []
for z in zones:
    board.Remove(z)
    _keep_alive.append(z)
for v in vias:
    board.Remove(v)
    _keep_alive.append(v)
board.Save(BOARD)

after = pcbnew.LoadBoard(BOARD)
print("saved: %d zone(s), %d GND via(s) remain; %d track/via item(s) total"
      % (len(list(after.Zones())),
         sum(1 for t in after.GetTracks()
             if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"),
         len(list(after.GetTracks()))))

"""Merge vias the repeated routing passes stacked on top of each other.

route.py does not treat a net's own vias as obstacles, so every re-run of an
ONLY_SET pass drops a fresh via wherever the previous pass had already put one.
Seven landed on (61.8, 35.2) and three on (81.8, 42.6) while +3V3 was stitched,
re-ripped and stitched again; a few more are 0.28 mm apart, close enough for
DRC's hole_to_hole.  All of them are the same net, so merging is free: the one
that stays has a 0.30 mm radius and covers the position the others occupied,
and every track that ended on a removed via therefore still lands on copper.

  python _car_dupes.py --dry
  python _car_dupes.py
"""
import collections
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = BOARD + ".pre-dupes.bak"
DRY = "--dry" in sys.argv
TOL = 0.40  # mm; covers both exact duplicates and the 0.283 mm pairs

board = pcbnew.LoadBoard(BOARD)

by_net = collections.defaultdict(list)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        by_net[t.GetNetname()].append((pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), t))

doomed = []
for net, items in sorted(by_net.items()):
    kept = []
    for x, y, via in items:
        if any((x - kx) ** 2 + (y - ky) ** 2 <= TOL * TOL for kx, ky in kept):
            doomed.append((net, x, y, via))
        else:
            kept.append((x, y))
    if len(kept) != len(items):
        print("%-8s %d via(s) -> %d" % (net, len(items), len(kept)))

print("\nremoving %d stacked via(s)" % len(doomed))
for net, x, y, _ in doomed:
    print("   %-8s (%7.3f, %7.3f)" % (net, x, y))

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

_keep_alive = []
for _, _, _, via in doomed:
    board.Remove(via)
    _keep_alive.append(via)
board.Save(BOARD)

after = pcbnew.LoadBoard(BOARD)
n = sum(1 for t in after.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
print("saved: %d track/via item(s), %d via(s)" % (len(list(after.GetTracks())), n))

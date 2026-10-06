"""Rip the copper a routing pass added, keeping the copper it inherited.

route.py's incremental passes stitched +3V3's islands with fresh 0.30 mm traces.
Some of them run at y 13.2-13.4 across x 45..60 -- the pocket's southern edge is
y 13.8 -- so the escape corridor R7.1/R8.1 need is walled off by copper this
project laid, not by the designer's two 0.80 mm diagonals (x = 31.2+y and
x = 32.8+y), which are original and stay.

A track counts as "added" when the baseline has no track on the same net, layer
and width with the same endpoint pair; a via likewise on net and position.
Baseline is the pre-routing board, so the pass's own work is what goes.

  python _car_ripnew.py +3V3 YD-ESP32-S3-Carrier.kicad_pcb.pre-inc.bak --dry
  python _car_ripnew.py +3V3 YD-ESP32-S3-Carrier.kicad_pcb.pre-inc.bak
"""
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
import os
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
NET = sys.argv[1]
BASE = os.path.join(HERE, sys.argv[2])
DRY = "--dry" in sys.argv
BACKUP = BOARD + ".pre-ripnew.bak"

Q = 1000  # 1 um bucket: enough to absorb float noise on a 0.2 mm grid


def q(v):
    return int(round(pcbnew.ToMM(v) * Q))


# pcbnew.LoadBoard returns None for a .bak path -- it refuses the extension
# without raising, so hand it a copy under a .kicad_pcb name.
TMP = os.path.join(HERE, "_ripnew_base.kicad_pcb")
shutil.copyfile(BASE, TMP)
base = pcbnew.LoadBoard(TMP)
if base is None:
    sys.exit("could not load baseline %s" % BASE)
have_seg, have_via = set(), set()
for t in base.GetTracks():
    if t.GetNetname() != NET:
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        have_via.add((q(s.x), q(s.y)))
    else:
        a, c = t.GetStart(), t.GetEnd()
        e = ((q(a.x), q(a.y)), (q(c.x), q(c.y)))
        have_seg.add((t.GetLayer(), min(e), max(e)))
print("baseline %s: %d segment(s), %d via(s)"
      % (os.path.basename(BASE), len(have_seg), len(have_via)))

board = pcbnew.LoadBoard(BOARD)
doomed, kept_seg, kept_via = [], set(), set()
for t in board.GetTracks():
    if t.GetNetname() != NET:
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        key = (q(s.x), q(s.y))
        if key in have_via:
            kept_via.add(key)
        else:
            doomed.append((t, "via", (pcbnew.ToMM(s.x), pcbnew.ToMM(s.y))))
    else:
        a, c = t.GetStart(), t.GetEnd()
        e = ((q(a.x), q(a.y)), (q(c.x), q(c.y)))
        key = (t.GetLayer(), min(e), max(e))
        if key in have_seg:
            kept_seg.add(key)
        else:
            doomed.append((t, "seg", (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                                      pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))))

mm = 0.0
for t, kind, _ in doomed:
    if kind == "seg":
        mm += pcbnew.ToMM(t.GetLength())

print("keeps %d original segment(s), %d original via(s)"
      % (len(kept_seg), len(kept_via)))
print("removes %d added item(s), %.1f mm" % (len(doomed), mm))
for t, kind, pos in doomed:
    print("   %-3s %s" % (kind, "  ".join("%7.3f" % v for v in pos)))

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

_keep_alive = []
for t, _, _ in doomed:
    board.Remove(t)
    _keep_alive.append(t)
board.Save(BOARD)
print("saved")

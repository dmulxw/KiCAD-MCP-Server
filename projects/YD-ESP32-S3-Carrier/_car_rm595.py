"""Take the four 74HC595s and their decoupling off the carrier PCB.

The carrier schematic already dropped U3-U6 and C9-C12 -- the 595s live on the
touch panel now, near the pin header, where they belong.  The PCB never followed,
so it still carries eight parts whose only purpose was to drive ROW*/CSEL* from
the carrier.  _car_state.py measured the blast radius: those eight footprints,
19 tracks on DRV_CASC1/2/3 (the cascade links between the 595s, which evaporate
with them), and 82 track endpoints that terminate on a doomed pad.

This does the deletion only.  It deliberately does NOT try to fix the 82 loose
ends: they have to be re-routed against the surviving copper, and that is the
router's job, not a delete script's.  DRC after this step is the baseline that
re-route has to beat, so run it and keep the number.

Removing items while holding live SWIG proxies corrupts the object table, so
every proxy touched here stays referenced until the save completes.

  python _car_rm595.py --dry     # report only
  python _car_rm595.py           # writes the board
"""
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb.pre-rm595.bak")

DOOMED_FP = ["C9", "C10", "C11", "C12", "U3", "U4", "U5", "U6"]
DOOMED_NETS = {"DRV_CASC1", "DRV_CASC2", "DRV_CASC3"}

DRY = "--dry" in sys.argv

board = pcbnew.LoadBoard(BOARD)
before_tracks = len(list(board.GetTracks()))
before_fps = len(list(board.GetFootprints()))

# Resolve everything to plain data/proxies up front, before anything is removed.
doomed_fp = [board.FindFootprintByReference(r) for r in DOOMED_FP]
missing = [r for r, f in zip(DOOMED_FP, doomed_fp) if f is None]
if missing:
    sys.exit("not on the board: %s" % ", ".join(missing))
doomed_tracks = [t for t in board.GetTracks() if t.GetNetname() in DOOMED_NETS]

print("board: %d footprint(s), %d track/via item(s)"
      % (before_fps, before_tracks))
print("delete: %d footprint(s) %s" % (len(doomed_fp), " ".join(DOOMED_FP)))
print("delete: %d track(s) on %s"
      % (len(doomed_tracks), ", ".join(sorted(DOOMED_NETS))))

for f in doomed_fp:
    print("   %-4s %-10s at (%.2f, %.2f)"
          % (f.GetReference(), f.GetValue(),
             pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)))

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

# Keep every removed proxy alive to the end: destroying them while the board is
# still live corrupts SWIG's object table, and the next GetFootprints() would
# hand back raw SwigPyObjects.
_keep_alive = []

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

for t in doomed_tracks:
    board.Remove(t)
    _keep_alive.append(t)
for f in doomed_fp:
    board.Remove(f)
    _keep_alive.append(f)

# Drop the netinfo entries the 595s owned, so the board does not carry three nets
# with no pads.  Doing it by name means it also catches any that no item used.
nets = board.GetNetInfo()
for name in sorted(DOOMED_NETS):
    net = nets.GetNetItem(name)
    if net is not None:
        board.Remove(net)
        _keep_alive.append(net)
        print("removed net %s" % name)

# The flag is aResetTrackAndViaSizes: False keeps the per-net track/via sizes the
# board already set, which is what we want -- this pass must not resize anything.
board.SynchronizeNetsAndNetClasses(False)
board.Save(BOARD)

after = pcbnew.LoadBoard(BOARD)
print("saved: %d footprint(s), %d track/via item(s)  (%d fp, %d item removed)"
      % (len(list(after.GetFootprints())), len(list(after.GetTracks())),
         before_fps - len(list(after.GetFootprints())),
         before_tracks - len(list(after.GetTracks()))))
print("\nnow DRC it -- this is the baseline the re-route must beat:\n"
      "  kicad-cli pcb drc --format json --output _car_drc_rm595.json "
      "--severity-all \"%s\"\n"
      "  python _tp_drcsum.py _car_drc_rm595.json _car_drc_base.json" % BOARD)

"""Sweep the dead ends the 595 removal left behind, using DRC as the authority.

Deleting U3-U6/C9-C12 took their pads with them, and 82 track endpoints had been
terminating on those pads.  What survives is 19 tracks with a floating end and 3
vias stranded on one layer, all inside the strip the eight parts occupied
(x 76-93, y 65-70).

The first attempt at this reimplemented "is this endpoint connected" from
geometry and got it wrong twice over: it flagged all 187 GND stitch vias, which
are connected through the copper pour and not through any pad or track, and it
missed every real stub, because a stub's free end often lies on some other net's
centreline where the old fan-out crossed.  KiCad already worked all of this out
and wrote it to the DRC report, so this reads that instead of guessing.

Targets are matched back to board items on (net, layer, length), with the DRC's
reported position used only to break ties -- the position field is the item's
anchor, which for a track is not reliably its start.

`isolated_copper` is deliberately not handled here: those four are GND *fills*
that lost the copper bridging them, so the fix is a re-pour, not a deletion.

  python _car_trim.py --dry    # report only
  python _car_trim.py          # writes the board
"""
import io
import json
import os
import re
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb.pre-trim.bak")
DRC = os.path.join(HERE, "_car_drc_rm595.json")

DRY = "--dry" in sys.argv
LEN_TOL = 0.012      # mm
POS_TOL = 3.0        # mm

LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def parse(desc):
    """(net, layer, length) out of '走线 [ROW17] (F.Cu), 长度: 1.6000 mm'."""
    net = re.search(r"\[([^\]]+)\]", desc or "")
    lay = re.search(r"\((F\.Cu|B\.Cu)\)", desc or "")
    ln = re.search(r"([\d.]+)\s*mm", desc or "")
    return (net.group(1) if net else None,
            lay.group(1) if lay else None,
            float(ln.group(1)) if ln else None)


report = json.load(io.open(DRC, encoding="utf-8"))
want_tracks, want_vias = [], []
for v in report.get("violations", []):
    if v.get("type") not in ("track_dangling", "via_dangling"):
        continue
    for it in v.get("items", []):
        net, lay, ln = parse(it.get("description"))
        pos = it.get("pos") or {}
        if v["type"] == "track_dangling":
            want_tracks.append((net, lay, ln, pos.get("x"), pos.get("y")))
        else:
            want_vias.append((net, pos.get("x"), pos.get("y")))

print("DRC wants removed: %d track(s), %d via(s)"
      % (len(want_tracks), len(want_vias)))

board = pcbnew.LoadBoard(BOARD)

tracks, vias = [], []
for t in board.GetTracks():
    tn = t.GetNetname()
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        vias.append({"obj": t, "net": tn,
                     "x": pcbnew.ToMM(p.x), "y": pcbnew.ToMM(p.y)})
    else:
        p = t.GetPosition()
        tracks.append({"obj": t, "net": tn,
                       "len": pcbnew.ToMM(t.GetLength()),
                       "layer": t.GetLayer(),
                       "x": pcbnew.ToMM(p.x), "y": pcbnew.ToMM(p.y)})

doomed, used = [], set()


def take(cands, key):
    """Best unused candidate: exact-ish on key, nearest to the DRC position."""
    best, score = None, None
    for c in cands:
        if id(c["obj"]) in used:
            continue
        s = key(c)
        if s is None:
            continue
        if best is None or s < score:
            best, score = c, s
    if best is not None:
        used.add(id(best["obj"]))
    return best


for net, lay, ln, x, y in want_tracks:
    layid = LAYERS.get(lay)

    def key(c, net=net, layid=layid, ln=ln, x=x, y=y):
        if c["net"] != net or c["layer"] != layid:
            return None
        if ln is None or abs(c["len"] - ln) > LEN_TOL:
            return None
        d = ((c["x"] - x) ** 2 + (c["y"] - y) ** 2) ** 0.5 if x is not None else 0.0
        return d if d <= POS_TOL else None

    c = take(tracks, key)
    if c:
        doomed.append(c)
    else:
        print("   ! no track matches %s %s %.4f mm @ (%s, %s)" % (net, lay, ln, x, y))

for net, x, y in want_vias:
    def key(c, net=net, x=x, y=y):
        if c["net"] != net:
            return None
        d = ((c["x"] - x) ** 2 + (c["y"] - y) ** 2) ** 0.5 if x is not None else 0.0
        return d if d <= POS_TOL else None

    c = take(vias, key)
    if c:
        doomed.append(c)
    else:
        print("   ! no via matches %s @ (%s, %s)" % (net, x, y))

print("matched %d of %d target(s)" % (len(doomed), len(want_tracks) + len(want_vias)))
for c in doomed:
    print("   %-10s %-5s %8.4f mm  (%.2f, %.2f)"
          % (c["net"], LAYERS and "", c.get("len", 0.0), c["x"], c["y"]))

if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

# Keep every removed proxy alive past the save: destroying them while the board
# is live corrupts SWIG's object table.
_keep_alive = []
for c in doomed:
    board.Remove(c["obj"])
    _keep_alive.append(c["obj"])
board.Save(BOARD)

after = pcbnew.LoadBoard(BOARD)
print("saved: %d track/via item(s)  (%d -> %d)"
      % (len(list(after.GetTracks())), len(tracks) + len(vias),
         len(list(after.GetTracks()))))

"""How many nets can actually cross the pinch, and who is taking the rest?

The strip's 31 nets all have to get from the four 74HC595 output rows
(x >= 53) to the header pins (x <= 50.3).  Everything between them is a
channel, and a channel has a capacity: at a lane pitch of

    TRACK_W + clearance = 0.30 + 0.16 = 0.46 mm

a free band h mm tall carries floor(h / 0.46) tracks on one layer.  This
counts those bands on the board as it actually is, and names the object
responsible for every blocked stretch, so capacity can be argued about
instead of guessed at.

  python _cap.py [--board PATH] [--x0 A --x1 B] [--safety S] [--culprit]
"""
import importlib.util
import sys

import pcbnew

spec = importlib.util.spec_from_file_location(
    "roc", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
           r"\scripts\route-open-carrier.py")
roc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roc)
S = roc.S

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\_strip_empty.kicad_pcb")
SAFETY = 0.03
X0, X1 = 49.0, 54.5
Y0, Y1 = 42.0, 74.0
STEP = 0.05
CULPRIT = False
argv = sys.argv[1:]
for k, a in enumerate(argv):
    if a == "--board":
        BOARD = argv[k + 1]
    elif a == "--safety":
        SAFETY = float(argv[k + 1])
    elif a == "--x0":
        X0 = float(argv[k + 1])
    elif a == "--x1":
        X1 = float(argv[k + 1])
    elif a == "--culprit":
        CULPRIT = True

CLEAR = 0.16
LANE = roc.TRACK_W + CLEAR
track_keep = CLEAR + roc.TRACK_W / 2 + SAFETY
via_keep = CLEAR + roc.VIA_DIA / 2 + SAFETY

b = pcbnew.LoadBoard(BOARD)
CU = (pcbnew.F_Cu, pcbnew.B_Cu)

# Items, each as (shape, label, layer or None if on every copper layer).
items = []
for t in b.GetTracks():
    sh = roc.item_shape(t)
    if sh is None:
        continue
    if t.GetClass() == "PCB_VIA":
        items.append((sh, "via %s" % t.GetNetname(), None))
    else:
        lay = t.GetLayer()
        if lay in CU:
            items.append((sh, "trk %s" % t.GetNetname(), lay))
for fp in b.GetFootprints():
    for p in fp.Pads():
        sh = roc.item_shape(p)
        if sh is None:
            continue
        on = [l for l in CU if p.IsOnLayer(l)]
        if not on:
            continue
        lbl = "%s.%s %s" % (fp.GetReference(), p.GetNumber(), p.GetNetname())
        both = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        items.append((sh, "pad " + lbl, None if both else on[0]))


def blockers_at(x, y, keep):
    """Labels of every item that keeps a track centre out of (x, y)."""
    out = []
    for sh, lbl, lay in items:
        if roc.dist_item(x, y, sh) < keep - 1e-9:
            out.append(lbl)
    return out


print("board      %s" % BOARD.rsplit("\\", 1)[-1])
print("pinch band x %.2f .. %.2f   step %.2f   safety %.2f" %
      (X0, X1, STEP, SAFETY))
print("lane pitch %.3f mm (track %.2f + clearance %.2f); "
      "track keep %.3f, via keep %.3f\n" % (LANE, roc.TRACK_W, CLEAR,
                                            track_keep, via_keep))

xs = []
v = X0
while v <= X1 + 1e-9:
    xs.append(v)
    v += STEP

rows = int(round((Y1 - Y0) / STEP)) + 1
for lay in CU:
    runs = []            # (y_start, y_end, via_ok_anywhere)
    cur = None
    for j in range(rows):
        y = Y0 + j * STEP
        free = True
        via = True
        for x in xs:
            bs = blockers_at(x, y, track_keep)
            if bs:
                free = False
                break
        if free:
            for x in xs:
                if blockers_at(x, y, via_keep):
                    via = False
                    break
        if free:
            if cur is None:
                cur = [y, y, via]
            else:
                cur[1] = y
                cur[2] = cur[2] and via
        else:
            if cur is not None:
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)

    tot_lanes = 0
    print("=== %s : free bands crossing the whole pinch ===" %
          b.GetLayerName(lay))
    for a, c, via in runs:
        h = c - a + STEP
        lanes = int(h / LANE)
        if lanes < 1:
            continue
        tot_lanes += lanes
        print("   y %6.2f .. %6.2f   %5.2f mm  -> %2d lane(s)   %s"
              % (a, c, h, lanes, "via ok" if via else "no via in band"))
    print("   subtotal: %d lane(s) on %s\n" % (tot_lanes, b.GetLayerName(lay)))

if CULPRIT:
    print("=== who blocks the row centres ===")
    y = Y0
    while y <= Y1 + 1e-9:
        mid = (X0 + X1) / 2.0
        bs = blockers_at(mid, y, track_keep)
        uniq = []
        for lbl in bs:
            if lbl not in uniq:
                uniq.append(lbl)
        print("  y %6.2f  %s" % (y, ", ".join(uniq[:4]) if uniq else "-- free --"))
        y += 0.5

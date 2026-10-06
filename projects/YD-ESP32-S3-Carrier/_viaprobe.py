"""Can a via be placed anywhere near a 74HC595 output pad?

Every strip net that still fails does so at the same last step: the search
reaches the right place on B.Cu and there is no legal via to hop to the F.Cu
SMD pad.  This measures that directly -- for each output pad it reports the
nearest foreign copper and the nearest position where a via would actually be
legal, using the router's own geometry helpers.

  python _viaprobe.py [--pad-keep 0.54]
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

PAD_KEEP = 0.54
for k, a in enumerate(sys.argv):
    if a == "--pad-keep":
        PAD_KEEP = float(sys.argv[k + 1])

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
for k, a in enumerate(sys.argv):
    if a == "--board":
        BOARD = sys.argv[k + 1]
b = pcbnew.LoadBoard(BOARD)

CU = (pcbnew.F_Cu, pcbnew.B_Cu)

items = []          # (shape, net, label, on-copper)
for t in b.GetTracks():
    sh = roc.item_shape(t)
    if sh is None:
        continue
    lay = t.GetLayer() if t.GetClass() != "PCB_VIA" else None
    items.append((sh, t.GetNetname(), "track/%s" % t.GetClass(), lay))
for fp in b.GetFootprints():
    for p in fp.Pads():
        sh = roc.item_shape(p)
        if sh is None:
            continue
        on = [l for l in CU if p.IsOnLayer(l)]
        if not on:
            continue
        both = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        items.append((sh, p.GetNetname(),
                      "%s.%s" % (fp.GetReference(), p.GetNumber()),
                      None if both else on[0]))

PADS = []
for ref in ("U3", "U4", "U5", "U6"):
    fp = b.FindFootprintByReference(ref)
    for num in "12345678":
        for p in fp.Pads():
            if str(p.GetNumber()) == num:
                PADS.append(("%s.%s" % (ref, num), p))

print("pad_keep = %.2f mm  (via legal where every copper layer clears it)\n"
      % PAD_KEEP)
print("%-8s %-9s %-26s %8s   %s" %
      ("pad", "net", "nearest foreign copper", "dist", "best legal via"))
for label, p in PADS:
    net = p.GetNetname()
    c = p.GetPosition()
    cx, cy = c.x / S, c.y / S
    foreign = [it for it in items if it[1] != net]

    best = (1e9, None)
    for sh, nm, lbl, lay in foreign:
        if lay is not None and lay not in CU:
            continue
        d = roc.dist_item(cx, cy, sh)
        if d < best[0]:
            best = (d, lbl + ("/%s" % lay if lay is not None else ""))

    # nearest legal via centre: scan a fine patch around the pad
    found = None
    step = 0.1
    n = 14
    cands = []
    for ii in range(-n, n + 1):
        for jj in range(-n, n + 1):
            vx, vy = cx + ii * step, cy + jj * step
            cands.append((abs(ii) + abs(jj), vx, vy))
    cands.sort()
    for _, vx, vy in cands:
        ok = True
        for sh, nm, lbl, lay in foreign:
            if lay is not None and lay not in CU:
                continue
            if roc.dist_item(vx, vy, sh) < PAD_KEEP - 1e-9:
                ok = False
                break
        if ok:
            found = (vx, vy, ((vx - cx) ** 2 + (vy - cy) ** 2) ** 0.5)
            break

    if found:
        tag = "(%6.2f,%6.2f)  %.2fmm away" % found
    else:
        tag = "NONE within 1.4mm"
    flag = "" if found and best[0] >= PAD_KEEP else "   <-- pad centre itself blocked"
    print("%-8s %-9s %-26s %8.3f   %s%s"
          % (label, net, best[1][:26], best[0], tag, flag))

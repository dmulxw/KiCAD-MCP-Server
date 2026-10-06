"""Cut dead-end copper with KiCad's own DRC as the judge.

_car_stub.py decides connectivity from geometry -- endpoint within the two
half-widths of another segment, within a via pad, inside a pad's bounding box.
On one 0.283 mm IO9 diagonal it disagrees with KiCad: the far end sits 0.283 mm
from the next track's endpoint, inside the 0.30 mm sum of the two half-widths,
so the script calls it joined while KiCad still reports the end unconnected.
Bounding-box pads are the same kind of approximation.

Rather than tune the fudge factor, this asks KiCad.  Each round runs a real DRC,
takes every track_dangling / via_dangling, deletes the items it names, and
repeats -- because cutting one dead end exposes the next link of the chain.
The cut is by definition connectivity-neutral: an item KiCad reports as
dangling has nothing at that end to lose.

Two SWIG traps are handled here.  A track proxy from list(GetTracks()) goes
stale the moment board.Remove() touches the board, so every endpoint is read
into plain floats before the first removal -- reading it afterwards throws
'SwigPyObject' object has no attribute 'x'.  And the removed objects are held
in _keep_alive until the save completes, or the C++ side frees them under
proxies that are still referenced.

  python _car_stub2.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = BOARD + ".pre-stub2.bak"
RPT = os.path.join(HERE, "_drc_stub2.json")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
EPS = 0.02


def drc():
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--output", RPT,
                    "--severity-all", BOARD], capture_output=True, text=True)
    return json.load(open(RPT, encoding="utf-8"))


def dangling(d):
    out = []
    for v in d.get("violations", []):
        if v.get("type") not in ("track_dangling", "via_dangling"):
            continue
        for e in v.get("items", []):
            pos = e.get("pos") or {}
            m = re.search(r"([0-9.]+) mm", e.get("description") or "")
            out.append((v.get("type"), pos.get("x"), pos.get("y"),
                        float(m.group(1)) if m else None))
    return out


first = True
for rnd in range(1, 20):
    items = dangling(drc())
    if not items:
        print("round %d: no dangling items -- done" % rnd)
        break

    board = pcbnew.LoadBoard(BOARD)
    TO = pcbnew.ToMM
    allt = list(board.GetTracks())

    hit = None
    for kind, x, y, ln in items:
        for t in allt:
            is_via = isinstance(t, pcbnew.PCB_VIA)
            if (kind == "via_dangling") != is_via:
                continue
            if x is None:
                continue
            if is_via:
                s = t.GetStart()
                px, py, L = TO(s.x), TO(s.y), None
            else:
                L = TO(t.GetLength())
                px = py = None
                for e in (t.GetStart(), t.GetEnd()):
                    ex, ey = TO(e.x), TO(e.y)
                    if abs(ex - x) < 0.05 and abs(ey - y) < 0.05:
                        px, py = ex, ey
                        break
                if px is None:
                    continue
            if abs(px - x) > 0.05 or abs(py - y) > 0.05:
                continue
            if ln is not None and L is not None and abs(L - ln) > EPS:
                continue
            hit = t
            break
        if hit is None:
            print("   ! could not locate %s near (%s, %s) len=%s" % (kind, x, y, ln))
        else:
            break

    if hit is None:
        print("round %d: nothing locatable -- stopping" % rnd)
        break

    # read every field off the proxy *before* Remove() invalidates it
    if isinstance(hit, pcbnew.PCB_VIA):
        s = hit.GetStart()
        label = "   - via  (%7.3f,%7.3f)" % (TO(s.x), TO(s.y))
    else:
        a, c = hit.GetStart(), hit.GetEnd()
        label = ("   - %-6s %-5s (%7.3f,%7.3f)->(%7.3f,%7.3f) len=%.4f"
                 % (hit.GetNetname(), pcbnew.LayerName(hit.GetLayer()),
                    TO(a.x), TO(a.y), TO(c.x), TO(c.y), TO(hit.GetLength())))
    print(label)

    if first:
        shutil.copyfile(BOARD, BACKUP)
        print("backup -> %s" % BACKUP)
        first = False

    _keep_alive = [hit]
    board.Remove(hit)
    board.Save(BOARD)
    del allt

final = dangling(drc())
print("\nremaining dangling: %d" % len(final))
for k, x, y, ln in final:
    print("   %s at (%s, %s) len=%s" % (k, x, y, ln))

"""Bring the carrier PCB onto the schematic the 595 migration produced.

_car_parity.py is the measurement; this is the change.  The schematic was
redesigned when the four 74HC595s moved to the panel: the carrier no longer
carries the key matrix at all.  J8 and J10 are now the panel interface -- IO9
through IO12 on J8's first four pins, and everything else on both connectors
either GND or +3V3 -- and ROW0..ROW20 / CSEL0..CSEL9 ceased to exist as nets.

The board still holds all of it: 417 copper items over 1348 mm of bus, plus the
old pad assignment on 31 connector pins.  Neither shows up in a reference-level
diff, which is why _car_state.py called this board synced.

Two passes, in this order:

  1. Delete every track and via whose net has no schematic counterpart.  Done
     first, while the nets are still named, so the bus is removed as a set
     rather than inferred afterwards from orphaned geometry.
  2. Re-point the connector pads at the schematic's nets.  Every net named here
     already exists on the board (GND, +3V3, IO9-IO12), so nothing is created --
     only the assignment moves.

Then the nets the bus vacated are dropped from netinfo.  Pads are never deleted
and no footprint is touched: this board's parts are right, only its wiring moved.

  python _car_sync.py --dry
  python _car_sync.py
"""
import collections
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
SCH = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_sch")
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb.pre-sync.bak")
NETXML = os.path.join(HERE, "_car_net.xml")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

DRY = "--dry" in sys.argv

r = subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml",
                    "--output", NETXML, SCH], capture_output=True, text=True)
if r.returncode != 0:
    sys.exit("netlist export failed:\n%s\n%s" % (r.stdout, r.stderr))

sch, sch_nets = {}, set()
for net in ET.parse(NETXML).getroot().iter("net"):
    name = (net.get("name") or "").lstrip("/")
    if name.startswith("unconnected-"):
        continue
    sch_nets.add(name)
    for node in net.iter("node"):
        sch[(node.get("ref"), node.get("pin"))] = name

board = pcbnew.LoadBoard(BOARD)

# -- 1. copper on nets the schematic does not have -------------------------
dead = [t for t in board.GetTracks()
        if t.GetNetname() and t.GetNetname() not in sch_nets
        # never take copper a footprint owns -- U1's thermal vias are GND and
        # would survive this test, but a part-internal track would not
        and not (t.GetParent() is not None
                 and t.GetParent().GetClass() == "FOOTPRINT")]
by_net = collections.Counter(t.GetNetname() for t in dead)
print("obsolete copper: %d item(s) over %d net(s)" % (len(dead), len(by_net)))
print("   " + ", ".join("%s(%d)" % (n, c) for n, c in sorted(by_net.items())))

# -- 2. connector pads pointed at the wrong net ----------------------------
repoint = []
for f in board.GetFootprints():
    ref = f.GetReference()
    if ref.startswith("#"):
        continue
    for p in f.Pads():
        want = sch.get((ref, str(p.GetNumber())))
        if want and want != (p.GetNetname() or None):
            repoint.append((ref, str(p.GetNumber()), p.GetNetname() or "(none)",
                            want, p))

print("\npad reassignment: %d pad(s)" % len(repoint))
by_ref = collections.defaultdict(list)
for ref, pin, old, new, _ in repoint:
    by_ref[ref].append((pin, old, new))
for ref in sorted(by_ref):
    print("   %s: %s" % (ref, ", ".join("%s %s->%s" % t for t in by_ref[ref])))

leaving = sorted(by_net)
if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

_keep_alive = []

for t in dead:
    board.Remove(t)
    _keep_alive.append(t)

nets = board.GetNetInfo()
for name in leaving:
    ni = nets.GetNetItem(name)
    if ni is not None:
        board.Remove(ni)
        _keep_alive.append(ni)

for ref, pin, old, new, pad in repoint:
    ni = board.FindNet(new) if hasattr(board, "FindNet") else nets.GetNetItem(new)
    if ni is None:
        sys.exit("no net %r on the board to point %s.%s at" % (new, ref, pin))
    pad.SetNet(ni)

# False = aResetTrackAndViaSizes: this pass must not resize anything.
board.SynchronizeNetsAndNetClasses(False)
board.Save(BOARD)

after = pcbnew.LoadBoard(BOARD)
print("saved: %d track/via item(s), %d net(s)"
      % (len(list(after.GetTracks())), after.GetNetCount()))

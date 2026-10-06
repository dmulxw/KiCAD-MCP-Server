"""Carrier schematic vs PCB, pad by pad -- the check _car_state.py does not make.

_car_state.py compares references, values and footprint ids, and by that measure
the board looks synced.  It is not.  The schematic was redesigned when the four
74HC595s moved to the panel: the key matrix left the carrier entirely, the panel
now takes IO9-IO12 plus power and ground on J8/J10, and ROW*/CSEL* no longer
exist as nets on this board at all.  A reference-level diff cannot see any of
that, because every reference still matches -- it is the *pad-to-net* assignment
that moved.

So this reads both sides down to (reference, pin) -> net and reports the
difference in both directions:

  STALE   a pad the PCB wires to a net the schematic no longer has (or no
          longer puts on that pin) -- the copper hanging off it is dead too
  MISSING a pad the schematic wires to a net the PCB does not -- the connector
          is short a connection and has to be routed

Anything listed under MISSING is routing work; anything under STALE is copper to
remove.  Both are needed before the board is the schematic.

  python _car_parity.py
"""
import collections
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
SCH = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_sch")
PCB = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
NETXML = os.path.join(HERE, "_car_net.xml")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

r = subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml",
                    "--output", NETXML, SCH], capture_output=True, text=True)
if r.returncode != 0:
    sys.exit("netlist export failed:\n%s\n%s" % (r.stdout, r.stderr))

sch = {}                       # (ref, pin) -> net
sch_nets = set()
for net in ET.parse(NETXML).getroot().iter("net"):
    name = (net.get("name") or "").lstrip("/")
    if name.startswith("unconnected-"):
        continue
    sch_nets.add(name)
    for node in net.iter("node"):
        sch[(node.get("ref"), node.get("pin"))] = name

board = pcbnew.LoadBoard(PCB)
pcb = {}
for f in board.GetFootprints():
    ref = f.GetReference()
    if ref.startswith("#"):
        continue
    for p in f.Pads():
        # "" and None both mean "no net"; collapsing them here keeps the diff
        # from reporting every unrouted pad on the board as a mismatch.
        pcb[(ref, str(p.GetNumber()))] = p.GetNetname() or None

refs = sorted({k[0] for k in sch} | {k[0] for k in pcb})

stale, missing = [], []
for ref in refs:
    pins = sorted({k[1] for k in sch if k[0] == ref}
                  | {k[1] for k in pcb if k[0] == ref},
                  key=lambda s: (0, int(s)) if s.isdigit() else (1, s))
    for pin in pins:
        s = sch.get((ref, pin))
        p = pcb.get((ref, pin))
        if s is None and p:
            stale.append((ref, pin, p, "not in schematic at all"))
        elif p is None and s:
            missing.append((ref, pin, s, "no such pad on the PCB"))
        elif s != p:
            stale.append((ref, pin, p, "schematic says %s" % s))
            missing.append((ref, pin, s, "pcb says %s" % p))

print("=" * 72)
print("STALE  -- PCB pads wired to a net the schematic does not put there (%d)"
      % len(stale))
print("=" * 72)
per_ref = collections.defaultdict(list)
for ref, pin, p, why in stale:
    per_ref[ref].append((pin, p, why))
for ref in sorted(per_ref,
                  key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):] or 0))):
    print("\n%s (%d pad(s))" % (ref, len(per_ref[ref])))
    for pin, p, why in per_ref[ref]:
        print("   pad %-4s  pcb net %-10s  %s" % (pin, p or "(none)", why))

print()
print("=" * 72)
print("MISSING -- schematic pads the PCB does not wire that way (%d)"
      % len(missing))
print("=" * 72)
per_ref = collections.defaultdict(list)
for ref, pin, s, why in missing:
    per_ref[ref].append((pin, s, why))
for ref in sorted(per_ref,
                  key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):] or 0))):
    print("\n%s (%d pad(s))" % (ref, len(per_ref[ref])))
    for pin, s, why in per_ref[ref]:
        print("   pad %-4s  schematic net %-10s  %s" % (pin, s, why))

# Copper on nets the schematic does not have at all: it cannot be reached by any
# sync, so it will sit there forever unless it is named and removed.
dead = collections.Counter()
dead_mm = collections.Counter()
for t in board.GetTracks():
    n = t.GetNetname()
    if n and n not in sch_nets:
        if isinstance(t, pcbnew.PCB_VIA):
            dead[n] += 1
        else:
            dead[n] += 1
            dead_mm[n] += pcbnew.ToMM(t.GetLength())
print()
print("=" * 72)
print("OBSOLETE COPPER -- nets with no schematic counterpart at all (%d net(s))"
      % len(dead))
print("=" * 72)
for n, c in dead.most_common():
    print("   %-10s %3d item(s)  %8.1f mm" % (n, c, dead_mm[n]))
print("   %-10s %3d item(s)  %8.1f mm"
      % ("TOTAL", sum(dead.values()), sum(dead_mm.values())))

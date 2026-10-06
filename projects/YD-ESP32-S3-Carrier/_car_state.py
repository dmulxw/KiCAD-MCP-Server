"""Carrier schematic vs PCB: what the sync would delete, and what it would free.

The carrier's schematic now carries only the ESP32 module and its decoupling --
the four 74HC595s moved to the touch panel (they have to be on the panel, near
the pin header).  If the PCB was never re-synced after that change it still holds
the old population, and every ROW*/CSEL* net still terminates there, which is
exactly the copper the panel pass is fighting for.

This reads both sides so the sync's blast radius is known before it is run:
footprints the PCB would lose, nets that would leave the board, and how much
track/via copper those nets own -- the copper that then becomes reusable.

  "/c/Program Files/KiCad/10.0/bin/python.exe" -X utf8 _car_state.py
"""
import collections
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
SCH = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_sch")
PCB = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def sch_refs(path):
    """Reference -> value, via kicad-cli's netlist (authoritative, not a regex)."""
    out = os.path.join(tempfile.gettempdir(), "_car_state_net.xml")
    r = subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml",
                        "--output", out, path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("netlist export failed:\n%s\n%s" % (r.stdout, r.stderr))
        sys.exit(1)
    import xml.etree.ElementTree as ET
    root = ET.parse(out).getroot()
    refs = {}
    for comp in root.iter("comp"):
        # <comp ref="C1"> -- the reference is an attribute; Value is a child.
        ref = comp.get("ref")
        if ref and not ref.startswith("#"):
            refs[ref] = (comp.findtext("value"),
                         comp.findtext("footprint") or "")
    return refs


sch = sch_refs(SCH)
board = pcbnew.LoadBoard(PCB)
fp = {}
for f in board.GetFootprints():
    ref = f.GetReference()
    if not ref.startswith("#"):
        fp[ref] = (f.GetValue(), str(f.GetFPID().GetLibItemName()))

print("schematic: %d component(s)" % len(sch))
print("     pcb : %d footprint(s)" % len(fp))

only_pcb = sorted(set(fp) - set(sch), key=lambda r: (re.sub(r"\d", "", r),
                                                     int(re.sub(r"\D", "", r) or 0)))
only_sch = sorted(set(sch) - set(fp))
print("\nONLY ON THE PCB (%d) -- the sync would delete these:" % len(only_pcb))
for ref in only_pcb:
    print("   %-6s %s" % (ref, fp[ref][0]))
if only_sch:
    print("\nONLY IN THE SCHEMATIC (%d) -- the sync would add these:" % len(only_sch))
    for ref in only_sch:
        print("   %-6s %s" % (ref, sch[ref][0]))

# Anything a surgical delete would miss: the sync also rewrites values and
# footprint assignments on the shared references.
drift = [(r, sch[r][0], fp[r][0]) for r in sorted(set(sch) & set(fp))
         if sch[r][0] != fp[r][0]]
print("\nshared refs whose VALUE differs (%d):" % len(drift))
for r, sv, pv in drift:
    print("   %-6s schematic %-16s pcb %s" % (r, sv, pv))
if not drift:
    print("   (none)")

fdrift = [(r, sch[r][1], fp[r][1]) for r in sorted(set(sch) & set(fp))
          if sch[r][1] and sch[r][1].split(":")[-1] != fp[r][1]]
print("\nshared refs whose FOOTPRINT differs (%d):" % len(fdrift))
for r, sf, pf in fdrift:
    print("   %-6s schematic %-40s pcb %s" % (r, sf, pf))
if not fdrift:
    print("   (none)")

# Nets that exist only because of the doomed footprints: each surviving pad's net
# is kept, so anything whose every pad is on a doomed footprint disappears.
doomed = set(only_pcb)
net_pads = collections.defaultdict(list)
for ref, _ in fp.items():
    f = board.FindFootprintByReference(ref)
    for p in f.Pads():
        net_pads[p.GetNetname()].append(ref)

leaving = sorted(n for n, refs in net_pads.items()
                 if n and set(refs) <= doomed)
track_n = collections.Counter()
track_mm = collections.Counter()
via_n = collections.Counter()
for t in board.GetTracks():
    net = t.GetNetname()
    if isinstance(t, pcbnew.PCB_VIA):
        via_n[net] += 1
    else:
        track_n[net] += 1
        track_mm[net] += pcbnew.ToMM(t.GetLength())

print("\nnets that leave the board entirely (%d):" % len(leaving))
tot_t = tot_mm = tot_v = 0
for n in leaving:
    tot_t += track_n[n]
    tot_mm += track_mm[n]
    tot_v += via_n[n]
    print("   %-10s %3d track(s) %8.1f mm  %2d via" %
          (n, track_n[n], track_mm[n], via_n[n]))
print("   %-10s %3d track(s) %8.1f mm  %2d via" %
      ("TOTAL", tot_t, tot_mm, tot_v))

# A track that ends on a doomed pad loses its anchor when the pad goes.  Count
# them by whether *both* endpoints are anchored somewhere else -- a track with one
# free end can be trimmed, but one that only ever touched the doomed pad is scrap.
anchors = []
for ref, _ in fp.items():
    f = board.FindFootprintByReference(ref)
    for p in f.Pads():
        anchors.append((ref, p.GetBoundingBox()))
touching = collections.Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    for pt in (t.GetStart(), t.GetEnd()):
        for ref, bb in anchors:
            if ref in doomed and bb.Contains(pt):
                touching[t.GetNetname()] += 1
                break
print("\ntrack endpoints sitting on a doomed pad: %d over %d net(s)"
      % (sum(touching.values()), len(touching)))
for n, c in touching.most_common():
    print("   %-10s %d" % (n, c))

keep_n = sum(track_n[n] for n in net_pads if n and n not in set(leaving))
print("\ncopper staying on the board: %d track(s) over %d net(s)"
      % (keep_n, len([n for n in net_pads if n and n not in set(leaving)])))
print("current board total: %d track/via item(s)" % len(list(board.GetTracks())))

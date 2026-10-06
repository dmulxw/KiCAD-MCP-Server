"""Is there a GND plane the R pad-2 terminals could simply via into?"""
import json
from collections import Counter, defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
board = pcbnew.LoadBoard(BOARD)
S = 1e6

print("=== zones ===")
for i, z in enumerate(board.Zones()):
    r = z.GetBoundingBox()
    print("  %2d  net=%-8s layers=%s prio=%s  x %.2f..%.2f y %.2f..%.2f"
          % (i, str(z.GetNetname()),
             ",".join(z.GetLayerSet().Seq()[k].GetLayerName()
                      for k in range(len(z.GetLayerSet().Seq()))),
             z.GetAssignedPriority(),
             r.GetLeft() / S, r.GetRight() / S, r.GetTop() / S, r.GetBottom() / S))

print("\n=== GND copper by layer (segments) ===")
c = Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetNetname() == "GND":
        c[t.GetLayerName()] += 1
for k, v in c.most_common():
    print("   %-8s %4d" % (k, v))

print("\n=== current DRC unconnected, by net ===")
try:
    d = json.load(open("_tp_drc.json", encoding="utf-8"))
    u = d.get("unconnected_items", [])
    print("   %d unconnected item(s)" % len(u))
    tal = Counter()
    for it in u:
        nets = set()
        descs = []
        for i in it.get("items", []):
            descs.append(i.get("description", ""))
            nets.add(i.get("description", "").split("[")[-1].rstrip("]"))
        for n in nets:
            tal[n] += 1
    for n, v in tal.most_common():
        print("   %-10s %3d" % (n, v))
except Exception as e:
    print("   (no _tp_drc.json: %s)" % e)

"""Rip named nets off a copy of the board, to test a hypothesis without
touching the live file.

  python _rip.py OUT.kicad_pcb NET [NET ...]

Used to check the "the greedy pass used the output-pad row as a highway"
theory: delete the long strip-crossing runs and see whether a via becomes
legal at U3.1-U4.8.
"""
import sys

import pcbnew

SRC = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_pcb")

out = sys.argv[1]
nets = set(sys.argv[2:])

b = pcbnew.LoadBoard(SRC)
doomed = [t for t in b.GetTracks() if t.GetNetname() in nets]
for t in doomed:
    b.Remove(t)

print("ripped %d item(s) from %s" % (len(doomed), ", ".join(sorted(nets))))
b.Save(out)
print("saved", out)

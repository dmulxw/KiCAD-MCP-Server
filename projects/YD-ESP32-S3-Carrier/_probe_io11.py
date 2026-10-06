"""Where does IO11's successful route run?  That is the doorway.

IO10 and IO11 are mutually exclusive: dropping IO11 opens R7.1's pocket to the
whole board, dropping anything else does not.  So IO11's 55 segments fill the
only F.Cu exit from the audio-module zone (vias are banned there, so the exit
has to be on copper).  Printing them shows whether the slot can carry a second
trace and where.

  python _probe_io11.py
"""
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
board = pcbnew.LoadBoard(HERE + r"\YD-ESP32-S3-Carrier.kicad_pcb")
mm = pcbnew.ToMM

segs = []
for t in board.GetTracks():
    if t.GetNetname() != "IO11":
        continue
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition()
        print("VIA  (%7.3f, %7.3f)  d=%.2f" % (mm(p.x), mm(p.y), mm(t.GetWidth(pcbnew.F_Cu))))
        continue
    s, e = t.GetStart(), t.GetEnd()
    segs.append((t.GetLayer(), mm(s.x), mm(s.y), mm(e.x), mm(e.y), mm(t.GetWidth())))

for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    n = [s for s in segs if s[0] == layer]
    if not n:
        continue
    print("\n%s: %d segment(s)" % (pcbnew.LayerName(layer), len(n)))
    for _l, x1, y1, x2, y2, w in sorted(n, key=lambda s: -max(abs(s[1]-s[3]), abs(s[2]-s[4]))):
        print("   (%7.3f,%7.3f)-(%7.3f,%7.3f)  w=%.2f  len=%.3f"
              % (x1, y1, x2, y2, w, ((x2-x1)**2 + (y2-y1)**2) ** 0.5))

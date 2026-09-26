import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6
b = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
print("=== copper in x[100.0,102.0] y[126.0,131.0] on the CURRENT board ===")
hits = []
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    for (x, y) in ((s.x/S, s.y/S), (e.x/S, e.y/S)):
        if 100.0 <= x <= 102.0 and 126.0 <= y <= 131.0:
            hits.append(t); break
for t in hits:
    s, e = t.GetStart(), t.GetEnd()
    lay = b.GetLayerName(t.GetLayer())
    print("  %-8s %-6s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f"
          % (b.GetNetname(t.GetNetId()) if hasattr(b,'GetNetname') else t.GetNetname(),
             lay, s.x/S, s.y/S, e.x/S, e.y/S, t.GetWidth()/S))
print("  total %d segment(s)" % len(hits))
print()
print("=== pads in that window ===")
n = 0
for fp in b.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        if 100.0 <= c.x/S <= 102.0 and 126.0 <= c.y/S <= 131.0:
            print("  %s.%s net=%s at (%.3f,%.3f)" % (fp.GetReference(), p.GetNumber(),
                  p.GetNetname(), c.x/S, c.y/S)); n += 1
print("  total %d pad(s)" % n)

import pcbnew
b = pcbnew.LoadBoard("/workspace/projects/touch-panel/touch-panel.kicad_pcb")
S = 1e6
rows = {}
for t in b.GetTracks():
    n = t.GetNetname()
    if not n.startswith("ROW"):
        continue
    if t.Type() == pcbnew.PCB_VIA_T:
        rows.setdefault(n, []).append(("via", t.GetPosition().x/S, t.GetPosition().y/S))
for n in sorted(rows, key=lambda r: int(r[3:])):
    vs = sorted(rows[n], key=lambda v: v[2])
    near = [v for v in vs if v[2] > 235]
    print(f"{n:6s} vias={len(vs):3d}  near J1 (y>235): " +
          ", ".join(f"({v[1]:.3f},{v[2]:.3f})" for v in near[:4]))

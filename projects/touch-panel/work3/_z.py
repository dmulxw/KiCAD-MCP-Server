import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6
b = pcbnew.LoadBoard("_r2.kicad_pcb")
z = list(b.Zones())
print("zones: %d" % len(z))
for q in z:
    print("  net=%-8s layers=%s prio=%d filled=%s bbox=(%.3f,%.3f)-(%.3f,%.3f)"
          % (q.GetNetname(), [b.GetLayerName(l) for l in q.GetLayerSet().Seq()],
             q.GetAssignedPriority(), q.IsFilled(),
             q.GetBoundingBox().GetLeft()/S, q.GetBoundingBox().GetTop()/S,
             q.GetBoundingBox().GetRight()/S, q.GetBoundingBox().GetBottom()/S))
# GS: is CSEL2 / ROW17 really a single connected blob, and how close is the near miss?
for name in ("CSEL2", "ROW17"):
    its = [t for t in b.GetTracks() if t.GetNetname() == name]
    print("%s: %d track(s)+via(s), %d pad(s)"
          % (name, len(its),
             sum(1 for fp in b.GetFootprints() for p in fp.Pads()
                 if p.GetNetname() == name)))
    worst = []
    for i in range(len(its)):
        for j in range(i+1, len(its)):
            A, B = its[i], its[j]
            if not any(A.IsOnLayer(l) and B.IsOnLayer(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)):
                continue
            def e(t):
                s, e_ = t.GetStart(), t.GetEnd()
                return [(s.x/S, s.y/S), (e_.x/S, e_.y/S)]
            def d2s(p, t):
                s, e_ = t.GetStart(), t.GetEnd()
                ax, ay, bx, by = s.x/S, s.y/S, e_.x/S, e_.y/S
                dx, dy = bx-ax, by-ay
                L2 = dx*dx+dy*dy
                if L2 == 0:
                    return ((p[0]-ax)**2 + (p[1]-ay)**2)**0.5
                u = max(0.0, min(1.0, ((p[0]-ax)*dx + (p[1]-ay)*dy)/L2))
                return ((p[0]-(ax+u*dx))**2 + (p[1]-(ay+u*dy))**2)**0.5
            # endpoint-in-other rule
            gap = min(min(d2s(p, B) - B.GetWidth()/S/2 for p in e(A)),
                      min(d2s(p, A) - A.GetWidth()/S/2 for p in e(B)))
            worst.append((gap, e(A), e(B), A.GetWidth()/S, B.GetWidth()/S))
    worst.sort()
    for w in worst[:4]:
        print("   gap %+.4f  A %s w=%.2f   B %s w=%.2f" % (w[0], w[1], w[3], w[2], w[4]))

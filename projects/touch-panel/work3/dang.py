import math, pcbnew
S = 1e6
board = pcbnew.LoadBoard('_final.kicad_pcb')
GRAVE = []

def is_via(it):
    return isinstance(it, pcbnew.PCB_VIA)

def lay(it):
    if isinstance(it, pcbnew.PAD):
        return "PAD " + it.GetParent().GetReference()
    n = it.GetLayerSet().Seq()
    return pcbnew.LayerName(n[0]) if n else "?"

def near(pt, items, skip, layer):
    best = (1e18, None)
    for it in items:
        if it.m_Uuid.AsString() == skip:
            continue
        if not it.IsOnLayer(layer):
            continue
        if isinstance(it, pcbnew.PCB_TRACK) and not is_via(it):
            s, e = it.GetStart(), it.GetEnd()
            a = (s.x/S, s.y/S)
            b = (e.x/S, e.y/S)
            dx, dy = b[0]-a[0], b[1]-a[1]
            L2 = dx*dx+dy*dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((pt[0]-a[0])*dx + (pt[1]-a[1])*dy)/L2))
            d = math.hypot(pt[0]-(a[0]+t*dx), pt[1]-(a[1]+t*dy)) - it.GetWidth()/S/2
        else:
            s, e = it.GetPosition(), None
            d = math.hypot(pt[0]-s.x/S, pt[1]-s.y/S) - (it.GetWidth()/S/2 if is_via(it) else 0.0)
        if d < best[0]:
            best = (d, it)
    return best

tracks = list(board.GetTracks())
for t in tracks:
    if not isinstance(t, pcbnew.PCB_TRACK) or is_via(t):
        continue
    if t.GetNetname() != 'GND':
        continue
    s, e = t.GetStart(), t.GetEnd()
    L = math.hypot((e.x-s.x)/S, (e.y-s.y)/S)
    if abs(L - 1.4) > 1e-6:
        continue
    u = t.m_Uuid.AsString()
    for tag, pt in (("start", (s.x/S, s.y/S)), ("end", (e.x/S, e.y/S))):
        d, who = near(pt, tracks, u, t.GetLayer())
        print("%s (%.4f,%.4f)  nearest other copper %.4fmm  %s  %s" % (
            tag, pt[0], pt[1], d,
            "DANGLING" if d > 0.0001 else "touching",
            ("%s @(%.3f,%.3f)" % (lay(who), who.GetStart().x/S, who.GetStart().y/S))
            if who is not None and isinstance(who, pcbnew.PCB_TRACK) else ""))

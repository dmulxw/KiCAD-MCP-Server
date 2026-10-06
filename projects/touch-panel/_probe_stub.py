import pcbnew
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
# J1 pads 4 and 6
for fp in b.GetFootprints():
    if fp.GetReference()!="J1": continue
    for n in ("4","6"):
        p=fp.FindPadByNumber(n); q=p.GetPosition()
        print("J1 pad %s net=%s (%.3f,%.3f)"%(n,p.GetNetname(),q.x/S,q.y/S))
print()
for net in ("ROW3","ROW5"):
    print("=== %s tracks with y>230 (near J1) ==="%net)
    for t in b.GetTracks():
        if t.GetNetname()!=net: continue
        a,c=t.GetStart(),t.GetEnd()
        if max(a.y,c.y)/S < 230: continue
        if isinstance(t,pcbnew.PCB_VIA):
            print("   VIA (%.3f,%.3f)"%(a.x/S,a.y/S)); continue
        print("   TRK %-5s (%.3f,%.3f)->(%.3f,%.3f) len=%.4f"%(
            t.GetLayerName(),a.x/S,a.y/S,c.x/S,c.y/S,
            ((a.x-c.x)**2+(a.y-c.y)**2)**0.5/S))
print()
print("=== who is within 0.35mm of each stub end? ===")
allit=[]
for fp in b.GetFootprints():
    for p in fp.Pads(): allit.append((p,"PAD %s.%s [%s]"%(fp.GetReference(),p.GetNumber(),p.GetNetname())))
for t in b.GetTracks(): allit.append((t,"TRK %s [%s]"%(t.GetLayerName(),t.GetNetname())))
def segd(px,py,t):
    a,c=t.GetStart(),t.GetEnd()
    ax,ay,bx,by=a.x/S,a.y/S,c.x/S,c.y/S
    dx,dy=bx-ax,by-ay; L2=dx*dx+dy*dy
    tt=0 if L2==0 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L2))
    return ((px-(ax+tt*dx))**2+(py-(ay+tt*dy))**2)**0.5
for net,pad in (("ROW3","4"),("ROW5","6")):
    for t in b.GetTracks():
        if t.GetNetname()!=net: continue
        a,c=t.GetStart(),t.GetEnd()
        if max(a.y,c.y)/S < 230: continue
        print(" %s stub end (%.4f,%.4f):"%(net,c.x/S,c.y/S))
        best=[]
        for it,lab in allit:
            if it is t: continue
            if it.GetNetname()==net: continue
            d=segd(c.x/S,c.y/S,it) if isinstance(it,pcbnew.PCB_TRACK) else (
                ((c.x-it.GetPosition().x)**2+(c.y-it.GetPosition().y)**2)**0.5/S)
            if d<0.35: best.append((d,lab))
        for d,lab in sorted(best)[:6]: print("      d=%.4f %s"%(d,lab))

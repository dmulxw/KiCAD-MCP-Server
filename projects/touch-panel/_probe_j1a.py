import pcbnew
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
for fp in b.GetFootprints():
    if fp.GetReference()=="J1A":
        print("J1A @(%.2f,%.2f):"%(fp.GetPosition().x/S,fp.GetPosition().y/S))
        for p in fp.Pads():
            if p.GetNetname():
                q=p.GetPosition()
                print("   pin %-3s %-8s (%.2f,%.2f)"%(p.GetNumber(),p.GetNetname(),q.x/S,q.y/S))
print("=== GND items in the wall window (100.30,118.00)-(102.40,148.00) ===")
n=0; ys=[]
for it in b.GetTracks():
    if it.GetNetname()!="GND": continue
    bb=it.GetBoundingBox()
    if (bb.GetLeft()/S>=100.30 and bb.GetRight()/S<=102.40
            and bb.GetTop()/S>=118.00 and bb.GetBottom()/S<=148.00):
        n+=1; ys += [bb.GetTop()/S,bb.GetBottom()/S]
print("   %d GND segment(s); y %.2f .. %.2f"%(n,min(ys) if ys else -1,max(ys) if ys else -1))
for net in ("ROW3","ROW5"):
    xs=[];yy=[]
    for it in b.GetTracks():
        if it.GetNetname()!=net: continue
        bb=it.GetBoundingBox()
        xs += [bb.GetLeft()/S,bb.GetRight()/S]; yy += [bb.GetTop()/S,bb.GetBottom()/S]
    print("   %s copper: %d item(s) x %.2f..%.2f y %.2f..%.2f"%(
        net,len(xs)//2,min(xs),max(xs),min(yy),max(yy)))

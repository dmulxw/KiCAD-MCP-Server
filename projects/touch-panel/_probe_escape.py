import importlib.util, pcbnew
spec=importlib.util.spec_from_file_location("ron","scripts/route-open-nets.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S=1e6; W=0.2; CLEAR=0.2
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")

def minclear(p0,p1,net,layer):
    best=(9e9,None)
    for t in b.GetTracks():
        if t.GetNetname()==net: continue
        if not m.on_layer(t,layer): continue
        sh=m.item_shape(t)
        # sample along candidate
        for k in range(201):
            f=k/200.0
            px=p0[0]+(p1[0]-p0[0])*f; py=p0[1]+(p1[1]-p0[1])*f
            d=m.dist_item(px,py,sh)-W/2
            if d<best[0]: best=(d,"TRK %s @(%.2f,%.2f)"%(t.GetNetname(),t.GetStart().x/S,t.GetStart().y/S))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()==net: continue
            if not m.on_layer(p,layer): continue
            sh=m.item_shape(p)
            if sh[1]>max(p0[1],p1[1])+3 or sh[3]<min(p0[1],p1[1])-3: continue
            for k in range(201):
                f=k/200.0
                px=p0[0]+(p1[0]-p0[0])*f; py=p0[1]+(p1[1]-p0[1])*f
                d=m.dist_item(px,py,sh)-W/2
                if d<best[0]: best=(d,"PAD %s.%s"%(fp.GetReference(),p.GetNumber()))
    return best

for net,px,py,up,dn in (("ROW3",127.250,243.150,241.5,245.5),("ROW5",128.250,243.150,241.5,245.5)):
    print("="*62); print(net,"pad (%.3f,%.3f)  rule=%.1fmm"%(px,py,CLEAR))
    for lay,ln in ((pcbnew.F_Cu,"F.Cu"),(pcbnew.B_Cu,"B.Cu")):
        for dyy,dn_ in ((up,"UP  -y -> %.1f"%up),(dn,"DOWN +y -> %.1f"%dn)):
            c,what=minclear((px,py),(px,dyy),net,lay)
            ok="OK " if c>=CLEAR else "BAD"
            print("   %s %-16s %s minclear=%+.3f  %s"%(ln,dn_,ok,c,what or ""))

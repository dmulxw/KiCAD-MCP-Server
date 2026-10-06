import importlib.util, pcbnew
spec=importlib.util.spec_from_file_location("ron","scripts/route-open-nets.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
for netname, px, py in (("ROW3",127.250,243.150), ("ROW5",128.250,243.150)):
    print("="*66); print("%s  J1 pad at (%.3f, %.3f)"%(netname,px,py))
    hits=[]
    for t in b.GetTracks():
        sh=m.item_shape(t)
        if sh is None: continue
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not m.on_layer(t,lay): continue
            d=m.dist_item(px,py,sh)
            if d<2.5:
                nm=t.GetNetname()
                kind="VIA" if isinstance(t,pcbnew.PCB_VIA) else "TRK"
                if kind=="TRK":
                    s,e=t.GetStart(),t.GetEnd()
                    geo="(%.3f,%.3f)->(%.3f,%.3f) w=%.3f"%(s.x/S,s.y/S,e.x/S,e.y/S,t.GetWidth()/S)
                else:
                    geo="d=%.3f"%(t.GetFrontWidth()/S)
                hits.append((d,"%s %-7s %-9s %s"%(kind,b.GetLayerName(lay),nm,geo)))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            sh=m.item_shape(p)
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                if not m.on_layer(p,lay): continue
                d=m.dist_item(px,py,sh)
                if d<2.5 and not (abs(d)<1e-9):
                    c=p.GetPosition(); sz=p.GetSize()
                    hits.append((d,"PAD %-7s %-9s (%8.3f,%8.3f) %.2fx%.2f"%(fp.GetReference()+"."+p.GetNumber(),
                                 p.GetNetname(),c.x/S,c.y/S,sz.x/S,sz.y/S)))
    for d,s in sorted(hits)[:14]:
        print("   %7.3f mm  %s"%(d,s))

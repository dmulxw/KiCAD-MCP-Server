import importlib.util, pcbnew
spec=importlib.util.spec_from_file_location("ron","scripts/route-open-nets.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
items=[]
ref={}
for fp in b.GetFootprints():
    for p in fp.Pads():
        ref[id(p)]=fp.GetReference()
        items.append(p)
for t in b.GetTracks(): items.append(t)
def nm(it):
    if isinstance(it,pcbnew.PAD): return "%s.%s"%(ref.get(id(it),"?") ,it.GetNumber())
    return it.GetLayerName()
for net,(px,py) in [("ROW3",(127.25,241.40)),("ROW5",(128.25,241.40)),
                    ("ROW3",(127.25,243.15)),("ROW5",(128.25,243.15))]:
    print("=== %s  around (%.2f,%.2f) ==="%(net,px,py))
    rows=[]
    for it in items:
        if it.GetNetname()==net: continue
        if not m.on_layer(it,pcbnew.F_Cu): continue
        s=m.item_shape(it)
        if not s: continue
        d=m.dist_item(px,py,s)
        if d<0.60:
            if isinstance(it,pcbnew.PAD):
                p=it.GetPosition()
                rows.append((d,"PAD  %-9s %-8s (%.3f,%.3f) %.2fx%.2f"%(
                    it.GetNetname(),nm(it),p.x/S,p.y/S,it.GetSizeX()/S,it.GetSizeY()/S)))
            else:
                a,c=it.GetStart(),it.GetEnd()
                rows.append((d,"TRK  %-9s %-6s (%.3f,%.3f)->(%.3f,%.3f) w=%.2f"%(
                    it.GetNetname(),it.GetLayerName(),a.x/S,a.y/S,c.x/S,c.y/S,it.GetWidth()/S)))
    for d,s in sorted(rows): print("   d=%.4f %s"%(d,s))
    print()

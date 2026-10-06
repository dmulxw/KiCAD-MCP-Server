import importlib.util, pcbnew
spec=importlib.util.spec_from_file_location("ron","scripts/route-open-nets.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
W=0.2; CLEAR=0.2; SAFETY=0.04
keep=CLEAR+W/2+SAFETY

net="ROW3"
obst=[]
for t in b.GetTracks():
    if t.GetNetname()==net: continue
    s=m.item_shape(t)
    if s: obst.append((t,s))
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname()==net: continue
        s=m.item_shape(p)
        if s: obst.append((p,s))

def legal(x,y,layer):
    best=9e9
    for it,s in obst:
        if not m.on_layer(it,layer): continue
        d=m.dist_item(x,y,s)
        if d<best: best=d
        if best<keep: return False,best
    return best>=keep,best

STEP=0.2
print("F.Cu free-space map, J1 pad4 start (127.25,243.15).  keep=%.2f"%keep)
print("     " + "".join("%d"%(int((120+k*STEP))//10%10) for k in range(0,76)))
print("     " + "".join("%d"%(int((120+k*STEP))%10) for k in range(0,76)))
for j in range(0,61):
    y=248.0-j*STEP
    row=""
    for k in range(0,76):
        x=120.0+k*STEP
        ok,_=legal(x,y,pcbnew.F_Cu)
        mark="." if ok else "#"
        if abs(x-127.25)<0.2 and abs(y-243.15)<0.8: mark="S"
        row+=mark
    print("%6.2f %s"%(y,row))

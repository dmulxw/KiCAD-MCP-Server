import pcbnew
S=1e6
b=pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb.pre-route595.bak.kicad_pcb") if False else pcbnew.LoadBoard("_base_rt.kicad_pcb")
# 595 output pads: y ~ 70.675, x in the strip
outs={}
for fp in b.GetFootprints():
    for p in fp.Pads():
        pos=p.GetPosition(); x,y=pos.x/S,pos.y/S
        if abs(y-70.675)<0.05 and 50.0<x<95.0:
            outs.setdefault(p.GetNetname(),[]).append((x,fp.GetReference(),p.GetNumber()))
print("nets with a pad in the 595 output row (y=70.675):", len(outs))
for n in sorted(outs, key=lambda n: outs[n][0][0]):
    x,r,num=outs[n][0]
    print("  %-8s pad %-6s at x=%7.3f  (fp %s)"%(n,num,x,r))

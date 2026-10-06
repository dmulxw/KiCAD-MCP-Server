import importlib.util, pcbnew
spec=importlib.util.spec_from_file_location("ron","scripts/route-open-nets.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
print("=== ROW8 pads ===")
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname()=="ROW8":
            q=p.GetPosition()
            print("  %s.%s (%.3f,%.3f) %.2fx%.2f"%(fp.GetReference(),p.GetNumber(),q.x/S,q.y/S,
                  p.GetSizeX()/S,p.GetSizeY()/S))
print("=== ROW8 tracks (F.Cu/B.Cu) ===")
for t in b.GetTracks():
    if t.GetNetname()!="ROW8": continue
    a,c=t.GetStart(),t.GetEnd()
    if isinstance(t,pcbnew.PCB_VIA):
        q=t.GetPosition(); print("  VIA  (%.3f,%.3f) d=%.2f"%(q.x/S,q.y/S,t.GetFrontWidth()/S))
    else:
        print("  TRK  %-5s (%.3f,%.3f)->(%.3f,%.3f) w=%.2f"%(t.GetLayerName(),a.x/S,a.y/S,c.x/S,c.y/S,t.GetWidth()/S))

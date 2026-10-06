import pcbnew
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
for net in ("ROW3","ROW5"):
    print("="*60); print(net)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()==net:
                c=p.GetPosition()
                sz=p.GetSize()
                print("  PAD %-4s.%-3s (%8.3f,%8.3f) size %.3fx%.3f  THT=%s"
                      %(fp.GetReference(),p.GetNumber(),c.x/S,c.y/S,
                        sz.x/S,sz.y/S, p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH))
    for t in b.GetTracks():
        if t.GetNetname()==net:
            s,e=t.GetStart(),t.GetEnd()
            if isinstance(t,pcbnew.PCB_VIA):
                print("  VIA  (%8.3f,%8.3f) d=%.3f"%(s.x/S,s.y/S,t.GetFrontWidth()/S))
            else:
                print("  TRK %-5s (%8.3f,%8.3f)->(%8.3f,%8.3f) L=%.4f w=%.3f"
                      %(b.GetLayerName(t.GetLayer()),s.x/S,s.y/S,e.x/S,e.y/S,
                        (s-e).EuclideanNorm()/S,t.GetWidth()/S))

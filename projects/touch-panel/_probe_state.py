import pcbnew
S=1e6
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
bb=b.GetBoardEdgesBoundingBox()
print("board bbox: x %.2f..%.2f  y %.2f..%.2f  (%.2f x %.2f)"%(
    bb.GetLeft()/S,bb.GetRight()/S,bb.GetTop()/S,bb.GetBottom()/S,
    bb.GetWidth()/S,bb.GetHeight()/S))
print("footprints: %d   tracks: %d"%(len(b.GetFootprints()),len(b.GetTracks())))
for fp in b.GetFootprints():
    r=fp.GetReference()
    if r.startswith("J1"):
        p=fp.GetPosition()
        print("  %-6s %-40s (%.2f,%.2f) padcount=%d"%(r,fp.GetFPIDAsString(),p.x/S,p.y/S,len(fp.Pads())))

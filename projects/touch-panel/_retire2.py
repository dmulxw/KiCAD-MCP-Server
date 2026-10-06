import pcbnew
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
j1=[fp for fp in b.GetFootprints() if fp.GetReference()=="J1"][0]
for n in ("4","6"):
    p=j1.FindPadByNumber(n)
    print("retiring J1.%s (was %s)"%(n,p.GetNetname()))
    p.SetNetCode(0)
pcbnew.SaveBoard("touch-panel.kicad_pcb",b)
print("saved")

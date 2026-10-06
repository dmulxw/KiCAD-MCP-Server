import pcbnew, shutil
S=1e6
shutil.copyfile("touch-panel.kicad_pcb","_retire.kicad_pcb")
b=pcbnew.LoadBoard("_retire.kicad_pcb")
hdr=set(); j1nets=[]
for fp in b.GetFootprints():
    r=fp.GetReference()
    if r in ("J1A","J1B"):
        for p in fp.Pads():
            if p.GetNetname(): hdr.add(p.GetNetname())
    if r=="J1":
        print("J1 attrs: dnp=%s exclude_bom=%s"%(fp.IsDNP(),fp.IsExcludedFromBOM()))
        for p in fp.Pads():
            j1nets.append((p.GetNumber(),p.GetNetname()))
print("nets on J1A/J1B: %d"%len(hdr))
only=[(n,nm) for n,nm in j1nets if nm and nm not in hdr]
print("J1 nets NOT also on J1A/J1B: %s"%only)
j1=[fp for fp in b.GetFootprints() if fp.GetReference()=="J1"][0]
for n in ("4","6"):
    p=j1.FindPadByNumber(n)
    print("  retiring J1.%s (was %s)"%(n,p.GetNetname()))
    p.SetNetCode(0)
pcbnew.SaveBoard("_retire.kicad_pcb",b)
print("saved _retire.kicad_pcb")

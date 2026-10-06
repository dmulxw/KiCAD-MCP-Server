import pcbnew, shutil
S=1e6
src="touch-panel.kicad_pcb"; dst="_rip8.kicad_pcb"
shutil.copyfile(src,dst)
b=pcbnew.LoadBoard(dst)
doomed=[]
for t in b.GetTracks():
    if t.GetNetname()!="ROW8": continue
    if not isinstance(t,pcbnew.PCB_TRACK): continue
    if not t.IsOnLayer(pcbnew.F_Cu): continue
    a,c=t.GetStart(),t.GetEnd()
    ymin=min(a.y,c.y)/S; xmax=max(a.x,c.x)/S; xmin=min(a.x,c.x)/S
    if ymin>240.9 and xmax>107.5:
        doomed.append((t,"(%.3f,%.3f)->(%.3f,%.3f)"%(a.x/S,a.y/S,c.x/S,c.y/S)))
print("ripping %d ROW8 F.Cu escape segment(s):"%len(doomed))
for t,s in doomed: print("   ",s)
for t,_ in doomed: b.Remove(t)
pcbnew.SaveBoard(dst,b)
print("saved",dst)

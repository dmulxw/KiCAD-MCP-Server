import sys, os, shutil
sys.path.insert(0, os.getcwd())
import pcbnew
SRC = '../touch-panel.kicad_pcb'

# ---- variant A: clear the net on J1 pads 4 and 6 ----
shutil.copy(SRC, 'touch-panel.kicad_pcb')
b = pcbnew.LoadBoard('touch-panel.kicad_pcb')
j1 = [fp for fp in b.GetFootprints() if fp.GetReference() == 'J1'][0]
print("J1 IsDNP before = %s" % j1.IsDNP())
for n in ("4", "6"):
    p = j1.FindPadByNumber(n)
    print("  pad %s before: net='%s' code=%d" % (n, p.GetNetname(), p.GetNetCode()))
    p.SetNetCode(0)
    print("  pad %s after : net='%s' code=%d" % (n, p.GetNetname(), p.GetNetCode()))
pcbnew.SaveBoard('_noA.kicad_pcb', b)

# ---- variant B: mark J1 DNP ----
shutil.copy(SRC, '_noB.kicad_pcb')
b2 = pcbnew.LoadBoard('_noB.kicad_pcb')
j2 = [fp for fp in b2.GetFootprints() if fp.GetReference() == 'J1'][0]
j2.SetDNP(True)
print("variant B: J1 IsDNP now = %s" % j2.IsDNP())
pcbnew.SaveBoard('_noB.kicad_pcb', b2)

# ---- variant C: both ----
shutil.copy(SRC, '_noC.kicad_pcb')
b3 = pcbnew.LoadBoard('_noC.kicad_pcb')
j3 = [fp for fp in b3.GetFootprints() if fp.GetReference() == 'J1'][0]
j3.SetDNP(True)
for n in ("4", "6"):
    j3.FindPadByNumber(n).SetNetCode(0)
pcbnew.SaveBoard('_noC.kicad_pcb', b3)
print("wrote _noA (nets cleared), _noB (DNP), _noC (both)")

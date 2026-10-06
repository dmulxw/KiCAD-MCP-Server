import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import pcbnew, importlib.util
spec = importlib.util.spec_from_file_location("roc", "scripts/route-open-carrier.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b = pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb")
n = 0
for t in b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        sh = m.item_shape(t)
        if n < 3: print("via shape:", sh)
        n += 1
print("item_shape() called on %d vias -- no assert, no block" % n)

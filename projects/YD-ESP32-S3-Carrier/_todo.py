import importlib.util, os, shutil, pcbnew
shutil.copyfile("YD-ESP32-S3-Carrier.kicad_pcb.pre-route595.bak", "_todotmp.kicad_pcb")
spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
rt.BOARD = os.path.abspath("_todotmp.kicad_pcb")
board = pcbnew.LoadBoard(rt.BOARD)
ds = board.GetDesignSettings(); ds.m_MinClearance = pcbnew.FromMM(rt.CLEAR); ds.m_TrackMinWidth = pcbnew.FromMM(0.25)
router = rt.Router(board)
todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]
print("route.py todo: %d nets" % len(todo))
print(" ".join(sorted(todo)))
os.remove("_todotmp.kicad_pcb")

import pcbnew
BOARD = r"YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
d = {str(f.GetReference()): f for f in b.GetFootprints()}

def show(tag):
    for ref in ("U1", "C5"):
        fp = d[ref]
        try:
            pads = fp.Pads()
            n = len(list(pads))
            print(f"  {tag:<22} {ref}: {type(fp).__name__} / Pads -> {type(pads).__name__} ({n})", flush=True)
        except Exception as e:
            print(f"  {tag:<22} {ref}: {type(fp).__name__} / Pads RAISED {type(e).__name__}: {e}", flush=True)

show("fresh")
# mutate: place U1 the way place.py does, via the dict
fp = d["U1"]
fp.SetOrientationDegrees(0)
fp.SetPosition(pcbnew.VECTOR2I(0, 0))
for angle in (0, 90, 180, 270):
    fp.SetOrientationDegrees(angle)
    npads = len(list(fp.Pads()))
first = None
for p in fp.Pads():
    if str(p.GetNumber()) == "1":
        first = p
        break
print(f"  after posing U1: first pad found = {first is not None}", flush=True)
show("after posing U1")

# now a FindFootprintByReference call, as place.py's missing/SWAP pass does
_ = b.FindFootprintByReference("C5")
show("after FindFootprintByRef")

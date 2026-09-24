"""Which step of place.py breaks board.GetFootprints()?"""
import pcbnew, sys

BOARD = r"YD-ESP32-S3-Carrier.kicad_pcb"
BOARD_W, BOARD_H = 100.0, 64.0
DIRS = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def mm(v):
    return pcbnew.ToMM(v)


def probe(board, tag):
    try:
        n = len(list(board.GetFootprints()))
        print(f"  after {tag:<28} GetFootprints() -> {n}", flush=True)
        return True
    except Exception as e:
        print(f"  after {tag:<28} RAISED {type(e).__name__}", flush=True)
        return False


b = pcbnew.LoadBoard(BOARD)
probe(b, "load")

# step: the SWAP loop's lookups (no swap needed now)
for ref in ("H1", "H2", "H3", "H4"):
    fp = b.FindFootprintByReference(ref)
    if str(fp.GetFPID().GetLibItemName()) == "MountingHole_3.2mm_M3":
        continue
probe(b, "SWAP lookups")

# step: 10 iterations of the PLACE loop
PLACE = [("J1", "pad1", (11.0, 8.0), "down"), ("J2", "pad1", (36.4, 8.0), "down"),
         ("J3", "pad1", (46.0, 32.0), "right"), ("J4", "pad1", (82.0, 31.0), "down"),
         ("J5", "pad1", (43.6, 5.4), "right"), ("SW5", "pad1", (55.0, 7.0), "right"),
         ("SW1", "pad1", (44.5, 59.0), "right"), ("SW2", "pad1", (55.5, 59.0), "right"),
         ("SW3", "pad1", (66.5, 59.0), "right"), ("SW4", "pad1", (77.5, 59.0), "right")]
for i, (ref, padname, (tx, ty), direction) in enumerate(PLACE):
    fp = b.FindFootprintByReference(ref)
    fp.SetOrientationDegrees(0)
    fp.SetPosition(vec(0, 0))
    number = padname[3:]
    want = DIRS[direction]
    for angle in (0, 90, 180, 270):
        fp.SetOrientationDegrees(angle)
        first = None
        for p in fp.Pads():
            if str(p.GetNumber()) == number:
                first = p
                break
        best, bestd = None, None
        for p in fp.Pads():
            if p.GetNumber() == first.GetNumber():
                continue
            d = (p.GetPosition() - first.GetPosition()).EuclideanNorm()
            if bestd is None or d < bestd:
                best, bestd = p, d
        d = best.GetPosition() - first.GetPosition()
        dx, dy = mm(d.x), mm(d.y)
        if dx * want[0] + dy * want[1] > 0 and abs(dx * want[1] - dy * want[0]) < 0.02:
            break
    delta = vec(tx, ty) - first.GetPosition()
    fp.SetPosition(fp.GetPosition() + delta)
    if not probe(b, f"PLACE[{i}] {ref}"):
        sys.exit(1)

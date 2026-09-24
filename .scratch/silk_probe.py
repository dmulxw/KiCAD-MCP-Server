"""Measure F.SilkS text bboxes against footprint silk bboxes, to see what really overlaps."""
import pcbnew

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(BOARD)


def bb(o):
    b = o.GetBoundingBox()
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
            pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


texts = [d for d in board.GetDrawings()
         if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_TEXT"]
boxes = []
for fp in board.GetFootprints():
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            boxes.append((fp.GetReference(), bb(g)))
    rf = fp.Reference()
    if rf.GetLayer() == pcbnew.F_SilkS:
        boxes.append((fp.GetReference() + ":ref", bb(rf)))

hits = 0
for t in texts:
    tb = bb(t)
    for name, gb in boxes:
        if overlap(tb, gb):
            hits += 1
            print(f"  {t.GetText()!r:<10} {tuple(round(v,2) for v in tb)}  OVERLAPS  "
                  f"{name} {tuple(round(v,2) for v in gb)}")
if not hits:
    print("  no text-vs-footprint-silk overlap")
print(f"\n{hits} overlap(s); {len(texts)} silk text item(s), {len(boxes)} footprint silk item(s)")

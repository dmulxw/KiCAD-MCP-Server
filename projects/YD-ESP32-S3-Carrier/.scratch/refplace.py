"""Find a genuinely free spot for each reference field.

Hand-placing eight designators against two dozen pad boxes is how silk_over_copper
warnings get made in the first place, so this tries candidate positions around
each footprint and keeps the first that clears every other silk item and every
pad by SILK_CLEAR, using real bounding boxes rather than estimates."""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
BOARD_W, BOARD_H = 100.0, 64.0
SILK_CLEAR = 0.25          # wanted silk-to-anything air gap, mm
EDGE = 0.30                # keep text this far inside the board edge

b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
TARGETS = ["C5", "C6", "C8", "R3", "R4", "R5", "SW1", "SW2", "SW3", "SW4"]


def box_of(item):
    bb = item.GetBoundingBox()
    return (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))


def gap(a, c):
    """Signed separation between two boxes; <=0 means they overlap."""
    dx = max(a[0] - c[2], c[0] - a[2])
    dy = max(a[1] - c[3], c[1] - a[3])
    if dx > 0:
        return dx
    if dy > 0:
        return dy
    return max(dx, dy)


# every pad on the board, and every silkscreen item that is not a target field
pads = [box_of(p) for fp in b.GetFootprints() for p in fp.Pads()]
target_fields = {}
for fp in b.GetFootprints():
    if str(fp.GetReference()) in TARGETS:
        target_fields[str(fp.GetReference())] = fp.Reference()
obstacles = []
for fp in b.GetFootprints():
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            obstacles.append(("silk", box_of(g)))
    for f in fp.GetFields():
        if f.GetLayer() == pcbnew.F_SilkS and f.IsVisible() and f not in target_fields.values():
            obstacles.append((f"field {fp.GetReference()}.{f.GetName()}", box_of(f)))
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.F_SilkS:
        obstacles.append(("silk", box_of(d)))

print(f"{len(pads)} pads, {len(obstacles)} silk items as obstacles\n")

for ref in TARGETS:
    fp = b.FindFootprintByReference(ref)
    fld = fp.Reference()
    body = box_of(fp) if False else None
    bb = fp.GetBoundingBox(False, False)
    body = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
    cx, cy = (body[0] + body[2]) / 2.0, (body[1] + body[3]) / 2.0

    # try each candidate: set the field, measure its real box, score it
    cands = []
    for dist in (0.55, 0.75, 0.95, 1.20, 1.50, 1.90):
        cands += [("above", cx, body[1] - dist), ("below", cx, body[3] + dist),
                  ("left", body[0] - dist, cy), ("right", body[2] + dist, cy)]
    best = None
    for (where, x, y) in cands:
        fld.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        box = box_of(fld)
        if (box[0] < EDGE or box[1] < EDGE
                or box[2] > BOARD_W - EDGE or box[3] > BOARD_H - EDGE):
            continue
        worst = min([gap(box, p) for p in pads]
                    + [gap(box, o) for _, o in obstacles], default=99.0)
        if worst >= SILK_CLEAR:
            best = (where, x, y, box, worst)
            break
    if best is None:
        # keep the least-bad so the report still shows where it wanted to go
        scored = []
        for (where, x, y) in cands:
            fld.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            box = box_of(fld)
            scored.append((min([gap(box, p) for p in pads]
                               + [gap(box, o) for _, o in obstacles], default=99.0),
                           where, x, y, box))
        scored.sort(reverse=True)
        worst, where, x, y, box = scored[0]
        print(f"{ref:<4} NO CLEAN SPOT (best {where} {worst:+.3f} mm)")
        fld.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    else:
        where, x, y, box, worst = best
        print(f"{ref:<4} {where:<5} ({x:7.2f}, {y:6.2f})  box x {box[0]:7.2f}..{box[2]:<7.2f}"
              f" y {box[1]:6.2f}..{box[3]:<6.2f}  clear {worst:.2f} mm")

b.Save(BOARD)
print("\nsaved -- now re-run silk.py's neighbours / DRC to confirm")

"""The empty bay is rectangle-shaped.  Enumerate every board item -- drawing,
footprint graphic, footprint-embedded zone, pad -- whose box overlaps it and
lives on a copper layer."""
import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM

# bay rect, generously oversized
BX0, BY0, BX1, BY1 = 8.0, 13.0, 45.0, 30.0
bay = pcbnew.BOX2I(pcbnew.VECTOR2I(pcbnew.FromMM(BX0), pcbnew.FromMM(BY0)),
                   pcbnew.VECTOR2I(pcbnew.FromMM(BX1 - BX0), pcbnew.FromMM(BY1 - BY0)))

def box(bb, label):
    x0, y0 = mm(bb.GetLeft()), mm(bb.GetTop())
    x1, y1 = mm(bb.GetRight()), mm(bb.GetBottom())
    print(f"   {label:<58} x {x0:7.2f}..{x1:<7.2f} y {y0:7.2f}..{y1:<7.2f}", flush=True)

print("=== board drawings on copper ===", flush=True)
for d in b.Drawings():
    try:
        lay = str(d.GetLayerName())
    except Exception:
        continue
    if lay in ("F.Cu", "B.Cu") and d.GetBoundingBox().Intersects(bay):
        box(d.GetBoundingBox(), f"{lay} {d.GetClass()} {getattr(d,'GetShapeStr',lambda:'')()}")

print("=== footprint graphics / zones on copper ===", flush=True)
for fp in b.GetFootprints():
    for g in fp.GraphicalItems():
        try:
            lay = str(g.GetLayerName())
        except Exception:
            continue
        if lay in ("F.Cu", "B.Cu") and g.GetBoundingBox().Intersects(bay):
            box(g.GetBoundingBox(), f"{fp.GetReference()} {lay} {g.GetClass()}")
    for zz in fp.Zones():
        lb = zz.GetBoundingBox()
        kinds = []
        if zz.GetIsRuleArea():
            kinds.append("RULEAREA")
        for a, n in (("GetDoNotAllowZoneFills", "noPour"),
                     ("GetDoNotAllowTracks", "noTracks"),
                     ("GetDoNotAllowVias", "noVias"),
                     ("GetDoNotAllowPads", "noPads"),
                     ("GetDoNotAllowFootprints", "noFps")):
            try:
                if getattr(zz, a)():
                    kinds.append(n)
            except Exception:
                pass
        box(lb, f"{fp.GetReference()} ZONE {zz.GetLayerSet().FmtHex()} {'/'.join(kinds)}")

print("=== pads overlapping the bay ===", flush=True)
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetBoundingBox().Intersects(bay):
            box(p.GetBoundingBox(), f"pad {fp.GetReference()}.{p.GetNumber()} "
                                    f"net={p.GetNetname() or '-'}")

print("=== other footprints whose body box overlaps the bay ===", flush=True)
for fp in b.GetFootprints():
    bb = fp.GetBoundingBox(False, False)
    if bb.Intersects(bay):
        box(bb, f"body {fp.GetReference()} {fp.GetFPID().GetLibItemName()}")

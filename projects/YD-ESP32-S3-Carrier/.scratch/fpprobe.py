"""Dump pad geometry for the new SMD footprints, in footprint-local mm.

place.py anchors on pad 1, so what it needs to know is where every other pad sits
*relative to pad 1* at rotation 0, plus the courtyard extent.  Printing that here
beats guessing and re-running the placer until the courtyards stop overlapping.
"""
import pcbnew

FP = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"

PARTS = [
    ("Package_SO", "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm_ThermalVias"),
    ("Package_TO_SOT_SMD", "SOT-23-6"),
    ("Diode_SMD", "D_SMA"),
    ("Inductor_SMD", "L_Taiyo-Yuden_NR-60xx"),
    ("LED_SMD", "LED_0805_2012Metric"),
    ("Resistor_SMD", "R_0805_2012Metric"),
    ("Capacitor_SMD", "C_0805_2012Metric"),
    ("Capacitor_SMD", "C_1206_3216Metric"),
    ("Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical"),
    ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical"),
    ("MountingHole", "MountingHole_3.2mm_M3"),
]


def rect_of(b):
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
            pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))


def bb(shape_items):
    xs, ys = [], []
    for it in shape_items:
        x0, y0, x1, y1 = rect_of(it.GetBoundingBox())
        xs += [x0, x1]
        ys += [y0, y1]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def courtyard(fp):
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    # SHAPE_POLY_SET carries BBox(), not GetBoundingBox()
    if poly.OutlineCount() == 0:
        return None
    return rect_of(poly.BBox())


for lib, name in PARTS:
    fp = pcbnew.FootprintLoad(f"{FP}\\{lib}.pretty", name)
    if fp is None:
        print(f"!! {lib}:{name} NOT FOUND")
        continue
    pads = list(fp.Pads())
    p1 = next((p for p in pads if str(p.GetNumber()) == "1"), None)
    o = (pcbnew.ToMM(p1.GetPosition().x), pcbnew.ToMM(p1.GetPosition().y)) if p1 else (0, 0)
    bb_all = bb(pads)
    cy = courtyard(fp)
    print(f"\n=== {lib}:{name}  ({len(pads)} pads)")
    print(f"    pad bbox   ({bb_all[0]:6.3f},{bb_all[1]:6.3f})-({bb_all[2]:6.3f},{bb_all[3]:6.3f})"
          f"   size {bb_all[2]-bb_all[0]:.3f} x {bb_all[3]-bb_all[1]:.3f}")
    if cy:
        print(f"    crtyd bbox ({cy[0]:6.3f},{cy[1]:6.3f})-({cy[2]:6.3f},{cy[3]:6.3f})"
              f"   size {cy[2]-cy[0]:.3f} x {cy[3]-cy[1]:.3f}")
    for p in sorted(pads, key=lambda q: str(q.GetNumber())):
        x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        s = p.GetSize()
        print(f"      pad {str(p.GetNumber()):<3} rel({x-o[0]:+7.3f},{y-o[1]:+7.3f})  "
              f"size {pcbnew.ToMM(s.x):.2f}x{pcbnew.ToMM(s.y):.2f}  {p.GetLayerSet().FmtHex()}")

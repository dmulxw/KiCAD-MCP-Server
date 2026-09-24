"""What exactly is punched out of the F.Cu pour, and what board item is
responsible for each hole?  The filler's output is the authority: a hole in the
filled polygon is a region some copper-bearing item told the filler to clear."""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
board = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM

def boxes(z):
    out = []
    ps = z.RawPolysList(pcbnew.F_Cu) if z.GetLayer() == pcbnew.F_Cu else None
    return out

for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    layer = "F.Cu" if z.GetLayer() == pcbnew.F_Cu else "B.Cu"
    poly = z.GetFilledPolysList(z.GetLayer())
    for i in range(poly.OutlineCount()):
        ol = poly.Outline(i)
        for h in range(poly.HoleCount(i)):
            hp = poly.Hole(i, h)
            b = hp.BBox()
            w, ht = mm(b.GetWidth()), mm(b.GetHeight())
            area = abs(hp.Area()) / 1e12  # nm^2 -> mm^2
            if area < 1.0:
                continue
            print(f"{layer} hole#{i}.{h}  x {mm(b.GetLeft()):7.2f}..{mm(b.GetRight()):<7.2f}"
                  f" y {mm(b.GetTop()):7.2f}..{mm(b.GetBottom()):<7.2f}"
                  f"  {w:6.2f} x {ht:6.2f}  area {area:8.2f} mm2")
            # who is in there?
            padhits = []
            for fp in board.GetFootprints():
                for p in fp.Pads():
                    pb = p.GetBoundingBox()
                    if pb.Intersects(b):
                        pos = p.GetPosition()
                        padhits.append(f"pad {fp.GetReference()}.{p.GetNumber()} @"
                                       f"({mm(pos.x):.2f},{mm(pos.y):.2f}) "
                                       f"{mm(p.GetSize().x):.2f}x{mm(p.GetSize().y):.2f} "
                                       f"net={p.GetNetname() or '-'}")
            for t in board.GetTracks():
                tb = t.GetBoundingBox()
                if tb.Intersects(b):
                    kind = "VIA" if t.GetClass() == "PCB_VIA" else "trk"
                    s, e = t.GetStart(), t.GetEnd()
                    lay = "F.Cu" if t.IsOnLayer(pcbnew.F_Cu) else ("B.Cu" if t.IsOnLayer(pcbnew.B_Cu) else "?")
                    padhits.append(f"{kind} {t.GetNetname() or '-'} [{lay}] "
                                   f"({mm(s.x):.2f},{mm(s.y):.2f})-({mm(e.x):.2f},{mm(e.y):.2f})")
            for fp in board.GetFootprints():
                fb = fp.GetBoundingBox(False, False)
                if fb.Intersects(b):
                    padhits.append(f"<fp {fp.GetReference()} bbox x {mm(fb.GetLeft()):.2f}.."
                                   f"{mm(fb.GetRight()):.2f} y {mm(fb.GetTop()):.2f}..{mm(fb.GetBottom()):.2f}>")
            for hit in padhits[:24]:
                print("      ", hit)
            if len(padhits) > 24:
                print(f"       ... {len(padhits)-24} more")

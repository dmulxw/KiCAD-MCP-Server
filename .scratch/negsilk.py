"""Negative test: perturb one label on the board and confirm the check fires."""
import pcbnew
B = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"

def bb(o):
    b = o.GetBoundingBox()
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
            pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))

def gap(r, px, py):
    return ((max(r[0]-px,0,px-r[2]))**2 + (max(r[1]-py,0,py-r[3]))**2) ** 0.5

def judge(board, pinned):
    """pinned: {(ref,pin) -> replacement text} applied to the *nearest* label."""
    labels = [(d.GetText(), bb(d), d) for d in board.GetDrawings()
              if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_TEXT"]
    for (ref, pin), new in pinned.items():
        fp = board.FindFootprintByReference(ref)
        p = [q for q in fp.Pads() if str(q.GetNumber()) == pin][0]
        px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        t = min(labels, key=lambda v: gap(v[1], px, py))
        t[2].SetText(new)          # mutate in memory only; never saved
        print(f"  perturbed {ref}.{pin}: {t[0]!r} -> {new!r}")

print("case 1 -- swap two J3 signal labels (SDA <-> SCL):")
b = pcbnew.LoadBoard(B)
judge(b, {("J3", "1"): "SCL", ("J3", "2"): "SDA"})
print("  then re-running the check would report:")
labels = [(d.GetText(), bb(d)) for d in b.GetDrawings()
          if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_TEXT"]
j3 = {l for _, l, _ in [("", "SDA", ""), ("", "SCL", ""), ("", "MCK", ""), ("", "BCK", ""),
                        ("", "DI", ""), ("", "WS", ""), ("", "DO", ""), ("", "3V3", ""),
                        ("", "VCC", ""), ("", "GND", "")]}
cands = [(t, r) for t, r in labels if t in j3]
for pin, want in (("1", "SDA"), ("2", "SCL")):
    p = [q for q in b.FindFootprintByReference("J3").Pads() if str(q.GetNumber()) == pin][0]
    px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    got, d = min(((t, gap(r, px, py)) for t, r in cands), key=lambda v: v[1])
    print(f"    J3.{pin} printed {got!r}, want {want!r}  -> "
          f"{'FAIL (caught)' if got != want else 'pass (MISSED)'}")

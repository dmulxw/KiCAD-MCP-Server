"""Report pad geometry of every footprint on the carrier board.

Run with KiCad's bundled python:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/inspect_pads.py
"""
import pcbnew

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"

board = pcbnew.LoadBoard(BOARD)

for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
    ref = fp.GetReference()
    pads = list(fp.Pads())
    print(f"\n=== {ref}  ({fp.GetFPID().GetLibItemName()}) ===")
    print(f"    pads={len(pads)}  origin=({pcbnew.ToMM(fp.GetPosition().x):.3f}, "
          f"{pcbnew.ToMM(fp.GetPosition().y):.3f})  rot={fp.GetOrientationDegrees():.1f}")
    if not pads:
        print("    (no pads)")
        continue
    # positions are relative to the footprint origin in board coords because the
    # footprint sits at (0,0) right after sync -- so these ARE the local offsets.
    for p in sorted(pads, key=lambda p: str(p.GetNumber())):
        pos = p.GetPosition()
        size = p.GetSize()
        print(f"    pad {str(p.GetNumber()):>4}  at=({pcbnew.ToMM(pos.x):8.3f}, "
              f"{pcbnew.ToMM(pos.y):8.3f})  size=({pcbnew.ToMM(size.x):.2f}x"
              f"{pcbnew.ToMM(size.y):.2f})  drill={pcbnew.ToMM(p.GetDrillSize().x):.2f}"
              f"  attr={p.GetAttribute()}")
    bb = fp.GetBoundingBox(False, False)
    print(f"    bbox(no text) = x[{pcbnew.ToMM(bb.GetLeft()):.2f}..{pcbnew.ToMM(bb.GetRight()):.2f}] "
          f"y[{pcbnew.ToMM(bb.GetTop()):.2f}..{pcbnew.ToMM(bb.GetBottom()):.2f}]")

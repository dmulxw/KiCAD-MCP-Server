import pcbnew

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(BOARD)

for fp in board.GetFootprints():
    if fp.GetReference() not in ("SW5", "SW3", "SW4"):
        continue
    print(f"\n=== {fp.GetReference()} ({fp.GetFPID().GetLibItemName()}) ===")
    for p in sorted(fp.Pads(), key=lambda p: (str(p.GetNumber()), p.GetPosition().x)):
        pos = p.GetPosition()
        print(f"    pad {str(p.GetNumber()):>3} at=({pcbnew.ToMM(pos.x):8.3f},{pcbnew.ToMM(pos.y):8.3f})")
    bb = fp.GetBoundingBox(False, False)
    print(f"    bbox(no text)= x[{pcbnew.ToMM(bb.GetLeft()):.2f}..{pcbnew.ToMM(bb.GetRight()):.2f}]"
          f" y[{pcbnew.ToMM(bb.GetTop()):.2f}..{pcbnew.ToMM(bb.GetBottom()):.2f}]")

print("\n=== Edge.Cuts drawings ===")
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        print("  ", d.GetClass(), d.GetShapeStr() if hasattr(d, 'GetShapeStr') else '',
              "start", pcbnew.ToMM(d.GetStart().x), pcbnew.ToMM(d.GetStart().y),
              "end", pcbnew.ToMM(d.GetEnd().x), pcbnew.ToMM(d.GetEnd().y))

print("\n=== design settings ===")
ds = board.GetDesignSettings()
print("  min clearance mm:", pcbnew.ToMM(ds.m_MinClearance))
print("  track width mm:", pcbnew.ToMM(ds.GetCurrentTrackWidth()))
print("  copper layers:", board.GetCopperLayerCount())

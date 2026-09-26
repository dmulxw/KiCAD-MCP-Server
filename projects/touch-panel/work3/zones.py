import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6
b = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
zs = list(b.Zones())
print("zones: %d" % len(zs))
for k, z in enumerate(zs):
    bb = z.GetBoundingBox()
    lys = [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]
    print("  [%d] net=%-6s layers=%s  x %.3f..%.3f  y %.3f..%.3f  filled=%s"
          % (k, z.GetNetname(), ",".join(lys),
             bb.GetLeft()/S, bb.GetRight()/S, bb.GetTop()/S, bb.GetBottom()/S,
             z.IsFilled()))
print()
print("R4 footprint + pad geometry:")
for fp in b.GetFootprints():
    if fp.GetReference() == 'R4':
        print("  R4 at (%.3f,%.3f) rot=%.0f fp=%s" % (
              fp.GetPosition().x/S, fp.GetPosition().y/S, fp.GetOrientationDegrees()/10.0, fp.GetFPID().GetLibItemName()))
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            print("    pad %s net=%-6s size=%.3fx%.3f at (%.3f,%.3f) bbox x %.3f..%.3f y %.3f..%.3f"
                  % (p.GetNumber(), p.GetNetname(), p.GetSize().x/S, p.GetSize().y/S,
                     p.GetPosition().x/S, p.GetPosition().y/S,
                     bb.GetLeft()/S, bb.GetRight()/S, bb.GetTop()/S, bb.GetBottom()/S))

import importlib.util, os, pcbnew
spec = importlib.util.spec_from_file_location("roc", "scripts/route-open-carrier.py")
roc = importlib.util.module_from_spec(spec); spec.loader.exec_module(roc)
S = 1e6
board = pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb")
name = "ROW1"
own = roc.net_items(board, name)
print("own items for %s: %d" % (name, len(own)))
for it in own:
    if isinstance(it, pcbnew.PAD):
        p = it.GetPosition()
        print("   PAD %s.%-4s (%8.3f,%8.3f) size %.2fx%.2f layers=%s"
              % (roc.netname(it), it.GetNumber(), p.x/S, p.y/S,
                 it.GetSize().x/S, it.GetSize().y/S,
                 it.GetLayerSet().FmtHex() if hasattr(it.GetLayerSet(),'FmtHex') else "?"))
    else:
        print("   %s net=%s" % (it.GetClass(), roc.netname(it)))

others = [it for it in board.GetTracks() if it.GetNetname() != name]
for fp in board.GetFootprints():
    others.extend(p for p in fp.Pads() if p.GetNetname() != name)
print("\nothers count = %d" % len(others))

# what is index 2?
def desc(it):
    if isinstance(it, pcbnew.PAD):
        p = it.GetPosition()
        return "PAD %s.%-4s @(%8.3f,%8.3f) size %.2fx%.2f" % (
            roc.netname(it), it.GetNumber(), p.x/S, p.y/S,
            it.GetSize().x/S, it.GetSize().y/S)
    if isinstance(it, pcbnew.PCB_VIA):
        p = it.GetPosition()
        return "VIA %s @(%8.3f,%8.3f) d=%.2f" % (roc.netname(it), p.x/S, p.y/S, it.GetFrontWidth()/S)
    return "%s %s" % (it.GetClass(), roc.netname(it))

pad = roc.pick_start(board, name, {"J8","J10"})
pp = pad.GetPosition(); pc = (pp.x/S, pp.y/S)
print("start pad: %s  at %s" % (desc(pad), pc))

print("\n--- every other-net item within 1.6mm of the start pad centre ---")
r = pad.GetBoundingBox()
hits = []
for k, it in enumerate(others):
    sh = roc.item_shape(it)
    if sh is None: continue
    d = roc.dist_item(pc[0], pc[1], sh)
    if d < 1.6:
        hits.append((d, k, it))
for d, k, it in sorted(hits):
    print("  idx %-6d d=%+.3f  %s" % (k, d, desc(it)))
print("total near: %d (of which own-net pads are excluded)" % len(hits))

print("\n--- pad bbox of the 595 row around the start ---")
for it in own:
    if isinstance(it, pcbnew.PAD):
        p = it.GetPosition()
        if abs(p.y/S - pc[1]) < 0.01 and abs(p.x/S - pc[0]) < 3.0:
            b = it.GetBoundingBox()
            print("   %-6s centre(%8.3f,%8.3f) bbox x %.3f..%.3f  y %.3f..%.3f"
                  % (it.GetNumber(), p.x/S, p.y/S, b.GetLeft()/S, b.GetRight()/S,
                     b.GetTop()/S, b.GetBottom()/S))

import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
print('nets:', sorted(str(n) for n in board.GetNetsByName().keys())[:80])
for net in ('ROW3', 'ROW5'):
    ts = [t for t in board.GetTracks() if t.GetNetname() == net]
    print('=== %s : %d items ===' % (net, len(ts)))
    for t in ts:
        s, e = t.GetStart(), t.GetEnd()
        print('   %-9s %-5s w=%.3f (%.4f,%.4f)-(%.4f,%.4f)' % (
            type(t).__name__, t.GetLayerName(), t.GetWidth()/S,
            s.x/S, s.y/S, e.x/S, e.y/S))
    # pads on this net
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                pos = p.GetPosition()
                print('   PAD %s.%s (%.3f,%.3f)' % (fp.GetReference(), p.GetNumber(), pos.x/S, pos.y/S))

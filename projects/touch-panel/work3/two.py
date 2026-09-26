import io, json, sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6
d = json.load(io.open('_drc_base_now.json', encoding='utf-8'))
print("=== baseline DRC: %d violations, %d unconnected ==="
      % (len(d.get('violations', [])), len(d.get('unconnected_items', []))))
for u in d.get('unconnected_items', []):
    print("  unconnected:")
    for it in u.get('items', []):
        print("     %-10s %s" % (it.get('description', '?'), it.get('pos', {})))
print()
b = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
for fp in b.GetFootprints():
    if fp.GetReference() != 'J1':
        continue
    print("J1 = %s  at (%.3f,%.3f)" % (fp.GetFPID().GetLibItemName(),
          fp.GetPosition().x/S, fp.GetPosition().y/S))
    for p in fp.Pads():
        n = p.GetNetname()
        if n in ('ROW3', 'ROW5'):
            bb = p.GetBoundingBox()
            print("  J1 pad %-3s -> %-5s at (%.3f,%.3f) bbox x %.3f..%.3f y %.3f..%.3f  DNP=%s"
                  % (p.GetNumber(), n, p.GetPosition().x/S, p.GetPosition().y/S,
                     bb.GetLeft()/S, bb.GetRight()/S, bb.GetTop()/S, bb.GetBottom()/S,
                     fp.IsDNP()))

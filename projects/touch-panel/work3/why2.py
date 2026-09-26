"""Resolve each real-copper violation to the actual geometry on the board.

why.py printed descriptions; the JSON also carries UUIDs, and a UUID is an
exact handle on the track.  This prints start/end/length/layer/net for both
items of every shorting_items / tracks_crossing / clearance violation, so the
emitter defect can be classified rather than inferred:

  * endpoint at a pad centre  -> the `pre` stub (pad centre to first cell)
  * endpoint on a 0.05mm grid -> a path segment
  * endpoint elsewhere        -> the `post` stub (attach_pt projection)

The grid origin on this board is (89.45, 99.45) with step 0.100, so a path
vertex satisfies (x-89.45)/0.1 == integer within rounding.
"""
import json, sys, collections
import pcbnew

S = 1e6
GX, GY, STEP = 89.45, 99.45, 0.1

report = sys.argv[1] if len(sys.argv) > 1 else "_drc_r1.json"
board = pcbnew.LoadBoard(sys.argv[2] if len(sys.argv) > 2 else "_r1.kicad_pcb")

by_uuid = {}
for t in board.GetTracks():
    by_uuid[t.m_Uuid.AsString()] = t
allpads = []
for fp in board.GetFootprints():
    for p in fp.Pads():
        by_uuid[p.m_Uuid.AsString()] = p
        allpads.append((fp.GetReference(), p))

pads = [(p.GetPosition().x / S, p.GetPosition().y / S, fp.GetReference(),
         p.GetNumber())
        for fp in board.GetFootprints() for p in fp.Pads()]


def ongrid(v):
    return abs((v - GX) / STEP - round((v - GX) / STEP)) < 1e-4


def nearpad(x, y, r=0.02):
    for px, py, ref, num in pads:
        if abs(px - x) < r and abs(py - y) < r:
            return "%s.%s" % (ref, num)
    return None


def show(uuid):
    it = by_uuid.get(uuid)
    if it is None:
        return "   <uuid not on board>"
    if isinstance(it, pcbnew.PAD):
        c = it.GetPosition()
        ref = next((r for r, p in allpads if p.m_Uuid.AsString()
                    == uuid), "?")
        return ("   PAD %-6s %-6s net=%-8s at (%.3f, %.3f)"
                % (ref, it.GetNumber(),
                   it.GetNetname(), c.x / S, c.y / S))
    s, e = it.GetStart(), it.GetEnd()
    ax, ay, bx, by = s.x / S, s.y / S, e.x / S, e.y / S
    ln = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    kind = "VIA" if isinstance(it, pcbnew.PCB_VIA) else "TRK"
    out = ("   %s net=%-8s len=%7.4f  (%.3f, %.3f) -> (%.3f, %.3f)"
           % (kind, it.GetNetname(), ln, ax, ay, bx, by))
    if kind == "TRK":
        tags = []
        for xx, yy, w in ((ax, ay, "A"), (bx, by, "B")):
            g = ongrid(xx) and ongrid(yy)
            p = nearpad(xx, yy)
            tags.append("%s:%s%s" % (w, "grid" if g else "offgrid",
                                     ("=" + p) if p else ""))
        out += "\n        " + "  ".join(tags)
    return out


d = json.load(open(report, encoding="utf-8"))
v = d.get("violations", [])
counts = collections.Counter(x["type"] for x in v)

for t in ("shorting_items", "tracks_crossing", "clearance"):
    rows = [x for x in v if x["type"] == t]
    if not rows:
        continue
    print("=" * 78)
    print("%s  %d" % (t, len(rows)))
    for x in rows:
        print("  " + x.get("description", "")[:140])
        for e in x.get("items", []):
            print(show(e.get("uuid", "")))

print("=" * 78)
print("counts: %s" % dict(counts))

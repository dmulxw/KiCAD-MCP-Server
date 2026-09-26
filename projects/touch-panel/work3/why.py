"""What exactly are the 52 new copper errors?  Dump them with coordinates.

unconn.py counts by type; this prints the offending geometry, so the emitter
defect can be seen instead of inferred.  For each real-copper violation
(tracks_crossing / clearance / shorting_items) show both item descriptions and
the distance between them -- a short has distance 0, a graze has a small one.
"""
import json, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else "_drc_r1.json"
d = json.load(open(path, encoding="utf-8"))
v = d.get("violations", [])

WANT = {"tracks_crossing", "clearance", "shorting_items", "via_dangling",
        "track_dangling"}
by = collections.Counter(x["type"] for x in v)

for t in ("shorting_items", "tracks_crossing", "clearance"):
    rows = [x for x in v if x["type"] == t]
    if not rows:
        continue
    print("=" * 78)
    print("%s   %d" % (t, len(rows)))
    for x in rows[:14]:
        print("  %s" % x.get("description", "")[:150])
        for e in x.get("items", []):
            print("      - %s" % e.get("description", "")[:130])
    if len(rows) > 14:
        print("  ... %d more" % (len(rows) - 14))

# how many violation items sit at an exact grid coordinate (x.xx5 or similar),
# which would prove the emitter placed them -- the grid origin is (89.45,99.45)
print("=" * 78)
print("all types: %s" % dict(by))

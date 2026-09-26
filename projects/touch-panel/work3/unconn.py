"""Group a DRC report's unconnected_items and violations by net and by type.

The routing job is bounded by exactly this list, and nothing else.  Pass one or
more report paths; the first is treated as the one under discussion.
"""
import json, sys, collections, os

for path in sys.argv[1:]:
    if not os.path.exists(path):
        print("%s: missing" % path)
        continue
    d = json.load(open(path, encoding="utf-8"))
    v = d.get("violations", [])
    u = d.get("unconnected_items", [])
    print("=" * 72)
    print("%s   %d violation(s), %d unconnected item(s)" % (path, len(v), len(u)))

    print("\n-- violations by type --")
    for t, n in collections.Counter(x["type"] for x in v).most_common():
        print("   %-28s %d" % (t, n))

    print("\n-- unconnected by net --")
    nets = collections.Counter()
    for it in u:
        for e in it.get("items", []):
            desc = e.get("description", "")
            # "Track [ROW3] on F.Cu, ..." / "Pad 1 [GND] of J1A on ..."
            if "[" in desc and "]" in desc:
                nets[desc.split("[", 1)[1].split("]", 1)[0]] += 1
    for n, c in nets.most_common():
        print("   %-10s %3d" % (n, c))
    print("   %-10s %3d   (%d distinct net(s))"
          % ("TOTAL", sum(nets.values()), len(nets)))
    print(flush=True)

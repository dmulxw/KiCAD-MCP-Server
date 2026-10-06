"""Bucket a kicad-cli DRC JSON report by violation type and by unconnected net."""
import json, sys
from collections import Counter

p = sys.argv[1] if len(sys.argv) > 1 else "_drc_now.json"
d = json.load(open(p, encoding="utf-8"))

viol = d.get("violations", [])
unc = d.get("unconnected_items", [])
print("violations %d   unconnected %d" % (len(viol), len(unc)))

print("\n-- by type")
for t, n in Counter(v["type"] for v in viol).most_common():
    print("  %-32s %d" % (t, n))

print("\n-- by severity")
for t, n in Counter(v.get("severity", "?") for v in viol).most_common():
    print("  %-32s %d" % (t, n))

print("\n-- unconnected by net")
c = Counter()
for u in unc:
    nets = {it.get("description", "") for it in u.get("items", [])}
    nm = u.get("description", "") or ""
    c[nm] += 1
for nm, n in c.most_common(60):
    print("  %-46s %d" % (nm[:46], n))

if viol:
    print("\n-- first 12 violations")
    for v in viol[:12]:
        print("  [%s] %s" % (v["type"], v.get("description", "")[:110]))
        for it in v.get("items", [])[:2]:
            print("        %s" % it.get("description", "")[:110])

"""Print the unconnected items in full, so "2 items" becomes a diagnosis.

unconn.py counts by net; a count of 2 tells you one pair exists but not which
two things failed to meet.  This prints the item descriptions verbatim, one
block per unconnected entry, optionally filtered to nets named on argv.
"""
import json, sys, collections

report = sys.argv[1] if len(sys.argv) > 1 else "_drc_r2.json"
want = set(sys.argv[2:])

d = json.load(open(report, encoding="utf-8"))
u = d.get("unconnected_items", [])

nets = collections.Counter()
for it in u:
    for e in it.get("items", []):
        desc = e.get("description", "")
        if "[" in desc and "]" in desc:
            nets[desc.split("[", 1)[1].split("]", 1)[0]] += 1

print("%s: %d unconnected entr(ies)" % (report, len(u)))
print("pairs per net: %s" % "  ".join(
    "%s=%d" % (n, c // 2) for n, c in nets.most_common()))

for n, c in nets.most_common():
    if want and n not in want:
        continue
    print("=" * 78)
    print("%s   %d unconnected pair(s)" % (n, c // 2))
    k = 0
    for it in u:
        ds = [e.get("description", "") for e in it.get("items", [])]
        if not any(("[%s]" % n) in x for x in ds):
            continue
        k += 1
        if k > 12:
            break
        for x in ds:
            print("    %s" % x[:120])
        print("    --")

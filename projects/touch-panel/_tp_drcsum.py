"""Summarise a kicad-cli DRC report by net, so a router pass can be judged.

route_all() scores only the nets in `todo`.  With RIPPABLE on, rip() can lift any
net on the board, including the 213 the pass is not working on -- and if one of
those is laid back down badly or not at all, the score still goes up.  The [OK ]
lines cannot show that, and neither can a total unconnected count, because a pass
that fixes eight nets and breaks three looks identical to one that fixes five.

KiCad's own DRC is the authority here: it unions pads, tracks and vias exactly as
the fab will, and its unconnected list names the nets.  This reads that JSON and
prints, per net, how many unconnected items it has -- so two runs can be diffed by
net and a regression shows up as a net that went from 0 to non-zero.

  kicad-cli pcb drc --format json --output _drc.json --severity-all BOARD
  python _tp_drcsum.py _drc.json

Compares against a baseline JSON when one is given, printing only the movement:
nets that got worse are what a pass must not produce, whatever its score.

  python _tp_drcsum.py _drc_after.json _drc_base.json
"""
import collections
import io
import json
import re
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__.strip())

after = json.load(io.open(sys.argv[1], encoding="utf-8"))
base = json.load(io.open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else None


def by_net(report):
    """Unconnected count per net, and the violation type counts.

    Each unconnected entry is a pair of items that should have been joined.  The
    net is only in the items' free text, as a trailing [NET] -- e.g.
    "F.Cu 上 U2 的焊盘 7 [ROW15]" -- and KiCad localises that text, so the
    bracketed token is the one part of it that is stable across locales.
    """
    counts = collections.Counter()
    for item in report.get("unconnected_items", []):
        nets = set()
        for part in item.get("items", []):
            m = re.search(r"\[([^\]]+)\]\s*$", part.get("description", ""))
            if m:
                nets.add(m.group(1))
        # Both items name the same net when it is one; fall back to the entry
        # text so an unlabelled or malformed entry is still counted somewhere
        # rather than silently dropped.
        if not nets:
            nets = {"<unnamed>"}
        for net in nets:
            counts[net] += 1

    kinds = collections.Counter(v.get("type", "?")
                                for v in report.get("violations", []))
    return counts, kinds


ac, ak = by_net(after)
print("after: %d unconnected item(s) across %d net(s); %d violation(s)"
      % (sum(ac.values()), len(ac), sum(ak.values())))

if base is None:
    for net, n in ac.most_common():
        print("   %-14s %d" % (net, n))
    print("\nviolations by type:")
    for k, n in ak.most_common():
        print("   %-24s %d" % (k, n))
    sys.exit(0)

bc, bk = by_net(base)
print("base : %d unconnected item(s) across %d net(s); %d violation(s)"
      % (sum(bc.values()), len(bc), sum(bk.values())))

worse = [(n, bc.get(n, 0), ac.get(n, 0)) for n in set(bc) | set(ac)
         if ac.get(n, 0) > bc.get(n, 0)]
better = [(n, bc.get(n, 0), ac.get(n, 0)) for n in set(bc) | set(ac)
          if ac.get(n, 0) < bc.get(n, 0)]

print("\nBROKEN (%d) -- these are regressions, whatever the pass scored:" % len(worse))
for n, b, a in sorted(worse, key=lambda t: t[1] - t[2]):
    print("   %-14s %d -> %d" % (n, b, a))
print("\nfixed (%d):" % len(better))
for n, b, a in sorted(better, key=lambda t: t[2] - t[1]):
    print("   %-14s %d -> %d" % (n, b, a))

print("\nviolations by type: base -> after")
for k in set(ak) | set(bk):
    d = ak.get(k, 0) - bk.get(k, 0)
    if d:
        print("   %-24s %4d -> %4d  (%+d)" % (k, bk.get(k, 0), ak.get(k, 0), d))

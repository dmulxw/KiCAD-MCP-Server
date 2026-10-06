"""Every unconnected item, verbatim, grouped by the net's role.

_tp_unc.py counted them.  This prints what each one actually is -- the two
copper items DRC could not join -- so the groups stop being categories and
become a work list.  The three groups behave completely differently:

  A  the 595 daisy-chains (IO10/IO11/IO12/IO9/+3V3) -- zero or partial copper,
     must be routed down the west strip
  B  ROW*/CSEL* -- the R-column weave, needs a vertical the board does not have
  C  GND -- short dangling stubs, 长度 under a millimetre

  python _tp_uncdetail.py _base_drc.json
"""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "_base_drc.json"
d = json.load(open(path, encoding="utf-8"))
u = d.get("unconnected_items", [])

A = ("IO9", "IO10", "IO11", "IO12", "+3V3")
B = ("ROW", "CSEL")


def kind(net):
    if net is None:
        return "?"
    if net in A:
        return "A"
    if net.startswith(B):
        return "B"
    if net == "GND":
        return "C"
    return "?"


def net_of(desc):
    if "[" not in desc:
        return None
    return desc.rsplit("[", 1)[1].split("]", 1)[0].strip()


groups = defaultdict(list)
for it in u:
    items = it.get("items", [])
    nets = [net_of(i.get("description", "")) for i in items]
    g = kind(next((n for n in nets if n), None))
    groups[g].append((nets, items))

for g in sorted(groups):
    print("=" * 78)
    print("GROUP %s : %d entr(ies)" % (g, len(groups[g])))
    print("=" * 78)
    for (nets, items) in groups[g]:
        print("  %s" % "  <>  ".join(n or "?" for n in nets))
        for i in items:
            msg = i.get("description", "")
            pos = i.get("pos", {})
            print("      %-58s at (%.2f, %.2f)"
                  % (msg[:58], pos.get("x", 0), pos.get("y", 0)))
    print()

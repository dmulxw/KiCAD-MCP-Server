"""Exactly which nets the unconnected items belong to, per board.

The lift's own accounting (12 OK / 28 FAIL -> 25 OK / 15 FAIL) is the router's
view, not the authority.  The authority is kicad-cli DRC, whose unconnected_items
carry the net name in brackets inside each item description.  This prints that
tally side by side for the baseline and for any other board, so "the lift fixes
13 nets but strands the GND taps" is a measured claim, not an inference.

  python _tp_unc.py [_base_drc.json ...]
"""
import json
import sys
from collections import Counter, defaultdict


def net_of(desc):
    """Descriptions look like 'F.Cu 上 U2 的焊盘 7 [ROW15]'."""
    if "[" not in desc:
        return None
    tail = desc.rsplit("[", 1)[1]
    return tail.split("]", 1)[0].strip()


def show(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("%s: cannot read (%s)" % (path, e))
        return
    u = d.get("unconnected_items", [])
    nets = Counter()
    examples = defaultdict(list)
    for it in u:
        items = it.get("items", [])
        names = {net_of(i.get("description", "")) for i in items}
        names.discard(None)
        for n in names:
            nets[n] += 1
            if len(examples[n]) < 1:
                examples[n].append(
                    " <> ".join(i.get("description", "") for i in items))
    print("=== %s : %d unconnected entr(ies), %d distinct net(s) ==="
          % (path, len(u), len(nets)))
    for n, c in nets.most_common():
        print("   %-10s %3d   %s" % (n, c, examples[n][0][:120]))
    print()


for p in (sys.argv[1:] or ["_base_drc.json", "_nospine_drc.json", "_tp_drc.json"]):
    show(p)

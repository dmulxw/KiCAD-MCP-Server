"""What actually crosses the board-to-board connector.

The carrier's hard problem is 31 strip nets that all have to leave the four
74HC595 output rows and reach the header, and the header is where the bill
lands.  This reads both projects' netlists and prints the pins of the
connectors that join the two boards, net by net, so the cost of an
architecture can be counted in pins instead of argued about.

  python _bridge.py [--car PATH] [--tp PATH]
                    [--car-refs "J8 J10"] [--tp-refs "J1"]
                    [--drv "U3 U4 U5 U6"]
"""
import sys
import xml.etree.ElementTree as ET

HERE = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
CAR = HERE + r"\_car.net.xml"
TP = HERE + r"\_tp.net.xml"
CAR_REFS = ["J8", "J10"]
TP_REFS = ["J1"]
DRV = ["U3", "U4", "U5", "U6"]

argv = sys.argv[1:]
k = 0
while k < len(argv):
    a = argv[k]
    if a == "--car":
        CAR = argv[k + 1]
        k += 2
    elif a == "--tp":
        TP = argv[k + 1]
        k += 2
    elif a == "--car-refs":
        CAR_REFS = argv[k + 1].split()
        k += 2
    elif a == "--tp-refs":
        TP_REFS = argv[k + 1].split()
        k += 2
    elif a == "--drv":
        DRV = argv[k + 1].split()
        k += 2
    else:
        sys.exit("unknown option %s" % a)


def load(path):
    """(values, pin->net, net->[(ref, pin)]) for one exported netlist."""
    root = ET.parse(path).getroot()
    vals = {}
    for c in root.find("components").findall("comp"):
        vals[c.get("ref")] = c.findtext("value") or "?"
    pins, nets = {}, {}
    for n in root.find("nets").findall("net"):
        name = n.get("name")
        for nd in n.findall("node"):
            r, p = nd.get("ref"), nd.get("pin")
            pins.setdefault(r, {})[p] = name
            nets.setdefault(name, []).append((r, p))
    return vals, pins, nets


def pkey(p):
    try:
        return (0, int(p), "")
    except ValueError:
        return (1, 0, str(p))


def dump(tag, path, refs, vals, pins):
    """Print each named connector pin by pin; return net -> ['REF.PIN']."""
    print("\n===== %s   %s" % (tag, path))
    seen = {}
    found = False
    for r in refs:
        if r not in pins:
            continue
        found = True
        tab = pins[r]
        print("\n  %s  %s   %d pin(s)" % (r, vals.get(r, "?"), len(tab)))
        for p in sorted(tab, key=pkey):
            print("    %-4s %s" % (p, tab[p]))
            seen.setdefault(tab[p], []).append("%s.%s" % (r, p))
    if not found:
        print("  none of %s here; connector-ish refs:" % refs)
        for r, v in sorted(vals.items()):
            if "FPC" in str(v).upper() or "CONN" in str(v).upper():
                print("    %-6s %s" % (r, v))
    return seen


cv, cp, cn = load(CAR)
tv, tp, tn = load(TP)
print("carrier     %s : %d component(s), %d net(s)" % (CAR, len(cv), len(cn)))
print("touch-panel %s : %d component(s), %d net(s)" % (TP, len(tv), len(tn)))

cseen = dump("carrier", CAR, CAR_REFS, cv, cp)
tseen = dump("touch-panel", TP, TP_REFS, tv, tp)

cnames, tnames = set(cseen), set(tseen)
print("\n===== crossing")
print("  carrier connector net(s) : %d" % len(cnames))
print("  panel   connector net(s) : %d" % len(tnames))
print("  same name on both sides  : %d" % len(cnames & tnames))
for n in sorted(cnames - tnames):
    print("    carrier only : %-16s %s" % (n, " ".join(cseen[n])))
for n in sorted(tnames - cnames):
    print("    panel   only : %-16s %s" % (n, " ".join(tseen[n])))
for n in sorted(cnames & tnames):
    print("    both         : %-16s car %-22s tp %s"
          % (n, " ".join(cseen[n]), " ".join(tseen[n])))

for r in DRV:
    if r not in cp:
        continue
    outs = sorted({n for n in cp[r].values() if n in cnames})
    print("\n  %s (%s) drives %d connector net(s): %s"
          % (r, cv.get(r, "?"), len(outs), " ".join(outs)))

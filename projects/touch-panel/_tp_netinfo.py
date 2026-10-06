"""What does the migrated touch-panel schematic actually say now?

Prints every net that touches the new shift registers, their decoupling, the
interface connectors and the row pull resistors, in a form that can be diffed
against the PCB.

  python _tp_netinfo.py [--refs U3,U4,J1] [--all]
"""
import re
import sys
import xml.etree.ElementTree as ET

XML = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\_tp_net.xml"

argv = sys.argv[1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


REFS = opt("--refs", "")
WANT = set(r.strip() for r in REFS.split(",") if r.strip()) if REFS else None
SHOW_ALL = "--all" in argv
NETRE = opt("--net", "")
NETPAT = re.compile(NETRE) if NETRE else None
BRIEF = "--brief" in argv

root = ET.parse(XML).getroot()

comps = {}
for c in root.iter("comp"):
    ref = c.get("ref")
    comps[ref] = c.findtext("value") or ""

nets = []
for n in root.iter("net"):
    name = n.get("name") or n.get("code")
    nodes = []
    for nd in n.iter("node"):
        nodes.append((nd.get("ref"), nd.get("pin"),
                      nd.get("pinfunction") or ""))
    nets.append((name, nodes))


def sortkey(nm):
    return nm


hits = 0
for name, nodes in nets:
    refs_here = {r for r, _, _ in nodes}
    if NETPAT is not None:
        if not NETPAT.search(name):
            continue
    else:
        if WANT is not None and not (refs_here & WANT):
            continue
        if WANT is None and not SHOW_ALL:
            continue
    hits += 1
    print("%-22s %2d node(s)" % (name, len(nodes)))
    if BRIEF:
        continue
    for r, p, fn in sorted(nodes, key=lambda t: (t[0] or "", t[1] or "")):
        print("        %-6s pin %-4s %-12s %s"
              % (r, p, fn, comps.get(r, "")))

if not hits:
    print("no matching net; pass --refs U3,U4,... or --all")

print("\n=== component summary for the new parts")
for ref in sorted(comps):
    if ref.startswith(("U", "C")) and ref not in ("C1",):
        pass
print("total comps in netlist: %d" % len(comps))
for ref in sorted(comps):
    if ref in ("J1", "J1A", "J1B") or ref.startswith(("U", "C")):
        print("   %-6s %s" % (ref, comps[ref]))

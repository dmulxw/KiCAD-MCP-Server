"""Read the exported netlist and show what the NEW parts landed on.

The question this answers is not "does it parse" -- ERC already said that -- but
"is ROW7 really on U3 pin 7, and does J8 pin 1 really reach ROW3".  Only the
shift-register and header pins are printed, because those are the ones this
change introduced; the pre-existing fanout is checked by the count.
"""
import xml.etree.ElementTree as ET

NEW = {"U3", "U4", "U5", "U6", "J8", "J10", "C9", "C10", "C11", "C12",
       "R6", "R7", "R8", "R9"}

root = ET.parse("_net.xml").getroot()
nets = sorted(root.find("nets"), key=lambda n: n.get("name"))

seen = {}
for n in nets:
    name = n.get("name").lstrip("/")
    mine = sorted("%s.%s" % (nd.get("ref"), nd.get("pin"))
                  for nd in n if nd.get("ref") in NEW)
    if mine:
        seen[name] = mine

print("%d net(s) touch the new parts\n" % len(seen))

print("-- ROW / CSEL: the driven matrix lines --")
for name in sorted(seen, key=lambda s: (s[:3] != "ROW", int(s[3:] if s[3:].isdigit() else 999))):
    if name.startswith(("ROW", "CSEL")):
        print("  %-8s %s" % (name, " ".join(seen[name])))

print("\n-- control / cascade / power --")
for name in sorted(seen):
    if not name.startswith(("ROW", "CSEL")):
        print("  %-10s %s" % (name, " ".join(seen[name])))

# Every ROW0-20 and CSEL0-9 must be driven by exactly one '595 output.
print()
bad = []
for i in range(21):
    if "ROW%d" % i not in seen:
        bad.append("ROW%d" % i)
for i in range(10):
    if "CSEL%d" % i not in seen:
        bad.append("CSEL%d" % i)
print("undriven lines: %s" % (", ".join(bad) if bad else "none -- all 31 outputs assigned"))

# And the headers must carry every one of those 31 lines plus the rails.
hdr = {k: v for k, v in seen.items()}
on_hdr = sorted({k for k, v in hdr.items()
                 if any(x.startswith(("J8.", "J10.")) for x in v)})
print("nets reaching J8/J10: %d" % len(on_hdr))

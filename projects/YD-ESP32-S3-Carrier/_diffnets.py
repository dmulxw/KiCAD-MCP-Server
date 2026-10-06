"""Prove the parts the user said not to touch were not touched.

The instruction was specific: J3 (voice) and J4 (display) must not lose or gain
a single pin, and J9 / J7 / the charging circuit must stay put.  "I did not edit
them" is a claim about my own actions; this is a claim about the result, which
is the one that matters.  It diffs the (ref, pin) -> net map of the pre-595
backup against the current schematic.

A pin that moved net, appeared, or vanished in the protected set is a failure.
"""
import sys
import xml.etree.ElementTree as ET

PROTECTED = ["J3", "J4", "J7", "J9",
             "U1", "U2", "D2", "D3", "L1", "R2", "R3", "R4", "R5",
             "C5", "C6", "C7", "C8", "SW5", "J5"]


def load(path):
    root = ET.parse(path).getroot()
    m = {}
    for n in root.find("nets"):
        name = n.get("name").lstrip("/")
        for nd in n:
            m[(nd.get("ref"), nd.get("pin"))] = name
    return m


old = load("_net_base.xml")
new = load("_net.xml")

print("baseline pins %d   current pins %d" % (len(old), len(new)))

fails = []
for ref in PROTECTED:
    o = {k[1]: v for k, v in old.items() if k[0] == ref}
    n = {k[1]: v for k, v in new.items() if k[0] == ref}
    if not o and not n:
        fails.append("%s absent from BOTH (typo in watch list?)" % ref)
        continue
    if o == n:
        print("  %-4s OK  %2d pin(s) identical  %s"
              % (ref, len(n), " ".join("%s=%s" % kv for kv in
                                       sorted(n.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0))))
        continue
    for pin in sorted(set(o) | set(n)):
        if o.get(pin) != n.get(pin):
            fails.append("%s pin %s: %r -> %r" % (ref, pin, o.get(pin), n.get(pin)))

print()
if fails:
    print("*** PROTECTED PARTS CHANGED ***")
    for f in fails:
        print("   " + f)
    sys.exit(1)
print("all %d protected part(s) bit-identical -- J3/J4/J9/J7 and the charger untouched"
      % len(PROTECTED))

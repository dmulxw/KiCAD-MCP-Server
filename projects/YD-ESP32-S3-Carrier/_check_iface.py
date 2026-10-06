"""Do the two boards still agree on how they are wired to each other?

The panel's FPC J1 mates pin-for-pin with the carrier's J8 (pins 1-20) and J10
(pins 21-40).  The four control lines were renamed on both sheets independently,
so the only thing that proves the cable is still straight is comparing the two
netlists position by position -- which is also the one check that catches an
off-by-one in either map.
"""
import sys
import xml.etree.ElementTree as ET

CARRIER = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
           r"\_car_after.net.xml")
PANEL = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel\_tp2.net.xml")


def load(path):
    nets = {}
    for net in ET.parse(path).getroot().iter("net"):
        name = net.get("name", "").lstrip("/")
        for n in net.findall("node"):
            nets[(n.get("ref"), n.get("pin"))] = name
    return nets


def pin_of(nets, ref, pin):
    return nets.get((ref, str(pin)), "-- unassigned --")


car = load(CARRIER)
pan = load(PANEL)
print("carrier %d net(s), panel %d net(s)\n" % (len(set(car.values())),
                                                len(set(pan.values()))))

#: panel J1 pin -> (carrier connector, carrier pad)
mating = []
for n in range(1, 21):
    mating.append((n, "J8", n))
for n in range(21, 41):
    mating.append((n, "J10", n - 20))

bad = 0
print("panel J1   carrier        panel net    carrier net")
for j1, cref, cpin in mating:
    a = pin_of(pan, "J1", j1)
    b = pin_of(car, cref, cpin)
    ok = a == b
    bad += 0 if ok else 1
    print("  %-8s %-4s.%-3d     %-12s %-12s %s"
          % (j1, cref, cpin, a, b, "" if ok else "   <-- MISMATCH"))

print()
if bad:
    sys.exit("%d of 40 interface pins disagree" % bad)
print("all 40 interface pins agree -- the cable is straight")

# The panel drives its own strip lines now; make sure none of them leaked back
# onto the connector, which is what would happen if a label were missed.
leak = sorted(j1 for j1, _r, _p in mating
              if pin_of(pan, "J1", j1) in ("ROW0",) or
              pin_of(pan, "J1", j1).startswith(("ROW", "CSEL")))
print("panel J1 pins still carrying a ROW/CSEL line: %s"
      % (leak if leak else "none"))

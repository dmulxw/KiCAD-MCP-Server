"""Verify the carrier netlist after the shift registers left.

Reads the exported netlist, not the schematic, so it checks what KiCad actually
believes rather than what the edit intended.  Two things must hold: the panel
connector carries the six-signal interface and nothing else, and no ROW, CSEL or
cascade net survives anywhere on the board.
"""
import io
import re
import sys
import xml.etree.ElementTree as ET

NET = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\_car_after.net.xml"

tree = ET.parse(NET)
root = tree.getroot()
nets = {}
for net in root.iter("net"):
    name = net.get("name", "").lstrip("/")
    nets.setdefault(name, []).extend(
        (n.get("ref"), n.get("pin")) for n in net.findall("node"))

print("%s : %d net(s)\n" % (NET.rsplit("\\", 1)[-1], len(nets)))

# --- the interface at the two panel connectors -----------------------------
print("=== J8 / J10 nodes")
seen = {}
for name, nodes in nets.items():
    for ref, pin in nodes:
        if ref in ("J8", "J10"):
            seen[(ref, int(pin))] = name
for ref in ("J8", "J10"):
    row = []
    for pin in range(1, 21):
        row.append("%d:%s" % (pin, seen.get((ref, pin), "-- none --")))
    print("   %-4s %s" % (ref, "  ".join(row[:10])))
    print("        %s" % "  ".join(row[10:]))

print("\n=== the control lines")
for name in ("IO9", "IO10", "IO11", "IO12"):
    nodes = nets.get(name, [])
    print("   %-6s %d node(s): %s"
          % (name, len(nodes), " ".join("%s.%s" % n for n in sorted(nodes))))

print("\n=== power")
for name in ("GND", "+3V3"):
    print("   %-6s %d node(s)" % (name, len(nets.get(name, []))))

# --- nothing that the panel now generates itself ---------------------------
stale = sorted(n for n in nets
               if re.match(r"^(ROW\d+|CSEL\d+|DRV_CASC\d+)$", n))
print("\n=== nets that should no longer exist on the carrier")
if stale:
    for name in stale:
        print("   %-12s %s" % (name, " ".join("%s.%s" % n for n in nets[name])))
    sys.exit("\nFAIL: %d stale net(s)" % len(stale))
print("   none -- all 21 ROW, 10 CSEL and 3 cascade nets are gone")

# --- and the chips themselves ----------------------------------------------
left = [c.get("ref") for c in root.iter("comp")
        if c.get("ref") in ("U3", "U4", "U5", "U6", "C9", "C10", "C11", "C12")]
print("\n=== components that should no longer exist")
print("   %s" % (left if left else "none -- U3-U6 and C9-C12 are gone"))
if left:
    sys.exit("FAIL: %s" % left)

print("\nOK")

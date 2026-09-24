"""Count pins per net, straight out of the .kicad_sch text.

ERC's "label connected to only one pin" is a position, not a net name, so locate
the culprit by rebuilding the netlist by hand: collect every symbol instance's
absolute pin coordinates (rotation + mirror applied) and every label anchor, then
bucket both by name.
"""
import re

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")

src = open(SCH, encoding="utf-8", newline="").read()


def num(s):
    return round(float(s), 2)


# ---------------------------------------------------------------- lib pin map
# (symbol name -> [(number, x, y)]) in symbol-local mm, Y up per KiCad libs
lib = {}
for m in re.finditer(r'\t\t\(symbol "([^"]+)"\r\n(.*?)\n\t\t\)\r\n', src, re.S):
    name, body = m.group(1), m.group(2)
    pins = []
    for pm in re.finditer(
            r'\(pin \w+ \w+\r\n(?:.*?\r\n)*?\t\t\t\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)\r\n'
            r'(?:.*?\r\n)*?\t\t\t\t\(number "([^"]+)"', body):
        pins.append((pm.group(4), float(pm.group(1)), float(pm.group(2))))
    if pins:
        lib[name] = pins

# ------------------------------------------------------------ placed symbols
inst = []
for m in re.finditer(r'\t\(symbol\r\n(.*?)\n\t\)\r\n', src, re.S):
    b = m.group(1)
    libid = re.search(r'\(lib_id "([^"]+)"\)', b).group(1)
    at = re.search(r'\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', b)
    if not at:
        continue
    ref = re.search(r'\(property "Reference" "([^"]+)"', b)
    mir = re.search(r'\(mirror ([xy])\)', b)
    inst.append((ref.group(1) if ref else "?", libid.split(":")[-1],
                 float(at.group(1)), float(at.group(2)), float(at.group(3)),
                 mir.group(1) if mir else None))

# ------------------------------------------------------------------- labels
pins, labels = {}, {}
missing_lib = set()
for ref, sym, x, y, ang, mir in inst:
    if sym not in lib:
        missing_lib.add(sym)
        continue
    for num_, px, py in lib[sym]:
        # library Y is up, schematic Y is down
        px, py = px, -py
        a = ang % 360
        if a == 90:
            px, py = py, -px
        elif a == 180:
            px, py = -px, -py
        elif a == 270:
            px, py = -py, px
        if mir == "x":
            py = -py
        elif mir == "y":
            px = -px
        pins.setdefault(f"{ref}.{num_}", (num(x + px), num(y + py)))

for m in re.finditer(r'\(label "([^"]+)"\r\n\t\t\(at ([-\d.]+) ([-\d.]+)', src):
    labels.setdefault(m.group(1), []).append((num(m.group(2)), num(m.group(3))))

if missing_lib:
    print("symbols with no lib pin map:", sorted(missing_lib))

# a label binds to a net by name; pins bind by sitting on the label anchor
by_coord = {}
for k, xy in pins.items():
    by_coord.setdefault(xy, []).append(k)

nets = {}
for name, anchors in labels.items():
    nets.setdefault(name, set()).update(anchors and [])
for name, anchors in labels.items():
    for a in anchors:
        for k in by_coord.get(a, []):
            nets[name].add(k)

print(f"{len(labels)} label name(s), {len(pins)} pin(s)\n")
print(f"{'net':<14} {'#pin':>4}  pins")
for name in sorted(nets):
    ps = sorted(nets[name])
    flag = "  <-- LONE" if len(ps) < 2 else ""
    print(f"{name:<14} {len(ps):>4}  {', '.join(ps)}{flag}")

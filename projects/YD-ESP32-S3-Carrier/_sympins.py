"""Which label sits on which pin, symbol by symbol.

The carrier sheet is label-driven: every connection is a label parked on a pin
endpoint, and nothing else.  So "what does this chip connect to" is answered by
placing each symbol's pins on the sheet and asking what text is sitting there,
and "what happens if I delete this chip" is answered by the same list -- those
are exactly the labels that go dangling.

Library pins are Y-up; a sheet is Y-down; and these connectors are rotated a
quarter turn, so the naive (sx + lx, sy - ly) is wrong for half this board.

  python _sympins.py [REF ...] [--sch PATH] [--tol 0.01]
"""
import re
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
TOL = 0.01

refs = []
i = 1
while i < len(sys.argv):
    a = sys.argv[i]
    if a == "--sch":
        SCH = sys.argv[i + 1]
        i += 2
    elif a == "--tol":
        TOL = float(sys.argv[i + 1])
        i += 2
    else:
        refs.append(a)
        i += 1


def sub_block(text, start):
    d = 0
    s = e = False
    j = start
    while j < len(text):
        c = text[j]
        if s:
            if e:
                e = False
            elif c == "\\":
                e = True
            elif c == '"':
                s = False
        elif c == '"':
            s = True
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return text[start:j + 1]
        j += 1
    raise ValueError("unbalanced at %d" % start)


def lib_pins(text, lib_id):
    """{number: (x, y, name)} in library coordinates, Y up."""
    libs = [text[i0:i1] for h, i0, i1 in _sexp.children(text) if h == "lib_symbols"][0]
    at = libs.find('(symbol "%s"' % lib_id)
    if at < 0:
        return {}
    block = sub_block(libs, at)
    out = {}
    i = 0
    while True:
        i = block.find("(pin ", i)
        if i < 0:
            break
        form = sub_block(block, i)
        m = re.search(r"\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", form)
        n = re.search(r'\(number "([^"]+)"', form)
        nm = re.search(r'\(name "([^"]*)"', form)
        if m and n:
            out[n.group(1)] = (float(m.group(1)), float(m.group(2)),
                               nm.group(1) if nm else "")
        i += len(form)
    return out


def place(sx, sy, angle, mirror, lx, ly):
    """Library point -> sheet point for one instance.

    Library Y runs up, the sheet's runs down, so even the unrotated case is a
    reflection:
        rot   0 : (sx + lx, sy - ly)
        rot  90 : (sx - ly, sy - lx)
        rot 180 : (sx - lx, sy + ly)
        rot 270 : (sx + ly, sy + lx)
    i.e. sheet = (sx + lx*cos - ly*sin, sy - lx*sin - ly*cos).  Getting the sign
    of the rotation wrong put J8's twenty pins ten millimetres off and made two
    fully connected connectors look like they had no labels at all.
    """
    if mirror == "y":
        lx = -lx
    elif mirror == "x":
        ly = -ly
    import math
    a = math.radians(angle % 360.0)
    cos, sin = math.cos(a), math.sin(a)
    return (sx + lx * cos - ly * sin, sy - lx * sin - ly * cos)


text = _sexp.load(SCH)
kids = _sexp.children(text)

labels = []
for head, i0, i1 in kids:
    if head != "label":
        continue
    at = _sexp.find_at(text[i0:i1])
    name = text[i0:i1].split('"')[1]
    if at:
        labels.append((at[0], at[1], name))

print("%d label(s), %d symbol(s) on %s\n"
      % (len(labels), sum(1 for h, _a, _b in kids if h == "symbol"),
         SCH.rsplit("\\", 1)[-1]))

for head, i0, i1 in kids:
    if head != "symbol":
        continue
    b = text[i0:i1]
    lib = re.search(r'\(lib_id "([^"]+)"\)', b)
    ref = re.search(r'\(property "Reference" "([^"]+)"', b)
    val = re.search(r'\(property "Value" "([^"]+)"', b)
    if not lib or not ref:
        continue
    if refs and ref.group(1) not in refs:
        continue
    pos = _sexp.find_at(b)
    mir = re.search(r"\(mirror ([xy])\)", b)
    pins = lib_pins(text, lib.group(1))
    print("=== %-6s %-30s %-14s at (%.2f, %.2f) rot %.0f%s"
          % (ref.group(1), lib.group(1), (val.group(1) if val else "")[:14],
             pos[0], pos[1], pos[2], " mirror " + mir.group(1) if mir else ""))
    for num in sorted(pins, key=lambda v: (not v.isdigit(), int(v) if v.isdigit() else v)):
        lx, ly, nm = pins[num]
        px, py = place(pos[0], pos[1], pos[2],
                       mir.group(1) if mir else None, lx, ly)
        hit = [n for x, y, n in labels
               if abs(x - px) <= TOL and abs(y - py) <= TOL]
        print("   pin %-3s %-9s at (%8.2f,%8.2f)  %s"
              % (num, nm[:9], px, py, " ".join(hit) if hit else "-"))

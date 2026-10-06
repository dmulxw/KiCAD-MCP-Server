"""Where a library symbol's pins land once the symbol is placed.

KiCad stores pin positions in the symbol's own frame: origin at the symbol
anchor, Y pointing up.  A sheet is Y-down, so a placed pin is
(sym_x + local_x, sym_y - local_y) for an unrotated, unmirrored instance --
which is how the four 595s are placed, so that is all this handles.

  python _pins.py LIBID [--sch PATH]
"""
import re
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel")
import _sexp

LIBID = sys.argv[1] if len(sys.argv) > 1 else "74xx:74HC595"
SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_sch")
if "--sch" in sys.argv:
    SCH = sys.argv[sys.argv.index("--sch") + 1]

text = _sexp.load(SCH)


def sub_block(text, start):
    """Span of the balanced form beginning at `start`."""
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
    raise ValueError("unbalanced form at %d" % start)


libs = [text[i0:i1] for h, i0, i1 in _sexp.children(text) if h == "lib_symbols"][0]
at = libs.find('(symbol "%s"' % LIBID)
block = sub_block(libs, at)
print("%s : %d byte(s) of definition" % (LIBID, len(block)))

# Each pin is (pin TYPE SHAPE (at X Y A) (length L) ... (name "N") (number "N")).
# The name/number order varies between generators, so read the number wherever
# it sits inside the pin's own balanced form rather than by a fixed pattern.
pins = {}
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
        pins[n.group(1)] = (float(m.group(1)), float(m.group(2)),
                            float(m.group(3)), nm.group(1) if nm else "")
    i += len(form)

print("pins: %d" % len(pins))
for num in sorted(pins, key=lambda v: int(v) if v.isdigit() else 0):
    x, y, a, nm = pins[num]
    print("   pin %-3s local (%7.2f, %7.2f, %3.0f)  %s" % (num, x, y, a, nm))

# Placement of every instance of it, so a caller can turn a pin number into a
# sheet coordinate.
print("\ninstances:")
for head, i0, i1 in _sexp.children(text):
    if head != "symbol":
        continue
    b = text[i0:i1]
    if '(lib_id "%s")' % LIBID not in b:
        continue
    ref = re.search(r'\(property "Reference" "([^"]+)"', b)
    pos = _sexp.find_at(b)
    print("   %-4s at %s" % (ref.group(1) if ref else "?", pos))
    for num in ("7", "9"):
        if num in pins:
            x, y, _a, nm = pins[num]
            print("        pin %-2s %-4s -> sheet (%.2f, %.2f)"
                  % (num, nm, pos[0] + x, pos[1] - y))

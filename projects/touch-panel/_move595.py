"""Cut the 31 strip drives loose from J1 and hand them to the onboard 595s.

Until now the panel received ROW0-20 and CSEL0-9 on J1 pins 1-31, all of them
generated on the carrier by four 74HC595s.  Those four chips are moving onto
this board, so those 31 labels come off J1 and the pins become the four shift
register control lines plus ground.

The new 40-pin map is exactly the old one with that substitution, which is why
it needs no thought: J1 pins 1-20 carry carrier J8 pad for pad and pins 21-40
carry J10 pad for pad, so the six signals that still cross are straight through
on both connectors at once.

  pin 1..4   IO9 IO10 IO11 IO12
  pin 5..36  GND
  pin 37..40 +3V3

Pins 32-40 already said GND/+3V3 and are left byte-identical; only 1-31 change.
The relocation of the labels onto the 595 outputs is done by batch_connect, so
this script only has to break the old attachment.

  python _move595.py [--sch PATH] [--dry-run]
"""
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_sch")
DRY = False

argv = sys.argv[1:]
for k, a in enumerate(argv):
    if a == "--sch":
        SCH = argv[k + 1]
    elif a == "--dry-run":
        DRY = True

#: J1's pin row.  Pin n sits at y = 11.43 + 2.54*(n-1); the label is placed on
#: the pin endpoint at x = 474.98, pointing left back into the symbol.
J1_X = 474.98
J1_Y0 = 11.43
PIN_PITCH = 2.54

NEW = {}
for i, name in enumerate(["IO9", "IO10", "IO11", "IO12"]):
    NEW[1 + i] = name
for n in range(5, 37):           # 5..31 change here; 32..36 are already GND
    NEW[n] = "GND"


def pin_y(n):
    return J1_Y0 + PIN_PITCH * (n - 1)


targets = {round(pin_y(n), 3): (n, name) for n, name in NEW.items()}

text = _sexp.load(SCH)
crlf = text.count("\r\n")
if crlf:
    # The batch_connect writer re-serialised the whole file with DOS line
    # endings; the sheet was LF before it, and a whole-file rewrite buries the
    # real edit in git.  Put the convention back.
    text = text.replace("\r\n", "\n")
    print("normalised %d CRLF line ending(s) back to LF" % crlf)

kids = _sexp.children(text)
edits = []
for head, i0, i1 in kids:
    if head != "label":
        continue
    at = _sexp.find_at(text[i0:i1])
    if at is None or abs(at[0] - J1_X) > 0.01:
        continue
    key = round(at[1], 3)
    if key not in targets:
        continue
    n, new = targets[key]
    block = text[i0:i1]
    q0 = block.index('"')
    q1 = block.index('"', q0 + 1)
    old = block[q0 + 1:q1]
    if old == new:
        continue
    edits.append((i0 + q0 + 1, i0 + q1, old, new, n))

print("J1 labels to change: %d" % len(edits))
for _a, _b, old, new, n in edits:
    print("   pin %-2d  %-8s -> %s" % (n, old, new))

if DRY:
    print("\ndry run -- not writing")
    sys.exit(0)

# Splice from the end so earlier offsets stay valid.
out = text
for a, b, _old, new, _n in sorted(edits, key=lambda e: -e[0]):
    out = out[:a] + new + out[b:]

_sexp.save(SCH, out)
print("\nwrote %s (%d byte(s))" % (SCH.rsplit("\\", 1)[-1], len(out)))

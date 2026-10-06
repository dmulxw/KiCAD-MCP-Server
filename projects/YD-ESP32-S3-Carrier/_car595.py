"""Move the four 74HC595s off the carrier sheet and reshape the panel interface.

The shift registers that generate ROW0-20 and CSEL0-9 are moving to the touch
panel, where they will sit next to the keys they drive.  On this sheet that is
pure subtraction: the four chips, their decoupling, the cascade links between
them, and the thirty-one signal labels on J8/J10 all go.

What replaces them at the connector is the four SPI-ish control lines plus
power, wired straight through from the ESP32:

    J8.1..4   IO9 IO10 IO11 IO12      SER SRCLK RCLK ~OE
    J8.5..20  GND
    J10.1..16 GND
    J10.17..20 +3V3                   (already correct, left untouched)

That is the same forty pins with the thirty-one signals replaced, and because
the panel's FPC pins 1-20 mate with J8 pad for pad and 21-40 with J10 pad for
pad, both ends of the cable change together without a mapping table.

R6-R9 stay.  They hold IO9-IO12 at defined levels before the ESP32 starts
driving them, and a floating ~OE on a board full of shift registers is a screen
full of phantom keypresses.

  python _car595.py [--sch PATH] [--dry-run]
"""
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _geom
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
DRY = False

argv = sys.argv[1:]
for k, a in enumerate(argv):
    if a == "--sch":
        SCH = argv[k + 1]
    elif a == "--dry-run":
        DRY = True

#: The four shift registers and the four capacitors that decoupled them.
GONE = ("U3", "U4", "U5", "U6", "C9", "C10", "C11", "C12")

#: The interface that replaces the thirty-one signals, by connector and pin.
PANEL = {}
for n, net in [(1, "IO9"), (2, "IO10"), (3, "IO11"), (4, "IO12")]:
    PANEL[("J8", n)] = net
for n in range(5, 21):
    PANEL[("J8", n)] = "GND"
for n in range(1, 17):
    PANEL[("J10", n)] = "GND"
for n in range(17, 21):
    PANEL[("J10", n)] = "+3V3"

TOL = 0.01


def near(a, b):
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def span_with_newline(text, i0, i1):
    """A child's span widened to swallow its own indentation and line break.

    Deleting only the (label ...) form would leave a line containing a single
    tab behind, once per removed child.
    """
    a, b = i0, i1
    if a >= 1 and text[a - 1] == "\t":
        a -= 1
    if text.startswith("\r\n", b):
        b += 2
    elif b < len(text) and text[b] == "\n":
        b += 1
    return a, b


text = _sexp.load(SCH)
print("%s : %d byte(s), %d CRLF, %d bare LF"
      % (SCH.rsplit("\\", 1)[-1], len(text), text.count("\r\n"),
         text.count("\n") - text.count("\r\n")))

syms = {s["ref"]: s for s in _geom.symbols(text)}
missing = [r for r in GONE if r not in syms]
if missing:
    sys.exit("symbols not found on the sheet: %s" % missing)

# --- every pin endpoint of every symbol that is leaving -------------------
doomed = {}
for ref in GONE:
    pts = _geom.pin_points(text, syms[ref])
    doomed[ref] = [p for p in pts]
    print("\n%s %s at %s -- %d pin(s)"
          % (ref, syms[ref]["lib_id"], syms[ref]["at"][:2], len(pts)))

dead_points = [(x, y) for ref in GONE for _n, x, y, _nm in doomed[ref]]

edits = []

# --- the labels parked on those pins --------------------------------------
# The last chip in the chain has two outputs with nothing to drive, which are
# held quiet by no_connect flags rather than labels.  Those flags sit on the
# same pins, so they have to leave together with the chip or they dangle.
killed = []
for head, i0, i1 in _sexp.children(text):
    if head not in ("label", "no_connect"):
        continue
    at = _sexp.find_at(text[i0:i1])
    if not at or not any(near((at[0], at[1]), p) for p in dead_points):
        continue
    name = text[i0:i1].split('"')[1] if head == "label" else "<no_connect>"
    killed.append((name, at[0], at[1]))
    edits.append(span_with_newline(text, i0, i1) + (name, "", "delete"))

print("\nlabels to delete: %d" % len(killed))
by_net = {}
for name, _x, _y in killed:
    by_net[name] = by_net.get(name, 0) + 1
for name in sorted(by_net):
    print("   %-10s x%d" % (name, by_net[name]))

# --- the symbols themselves ------------------------------------------------
for ref in GONE:
    s = syms[ref]
    edits.append(span_with_newline(text, s["i0"], s["i1"]) + (ref, "", "delete"))

# --- the interface at J8/J10 ----------------------------------------------
print("\ninterface rewrite:")
renames = 0
for ref in ("J8", "J10"):
    for num, x, y, _nm in _geom.pin_points(text, syms[ref]):
        want = PANEL[(ref, int(num))]
        hit = [(n, i0, i1) for n, lx, ly, _a, i0, i1 in _geom.labels(text)
               if near((lx, ly), (x, y))]
        if len(hit) != 1:
            sys.exit("%s pin %s at (%.2f, %.2f): expected 1 label, found %d %s"
                     % (ref, num, x, y, len(hit), [h[0] for h in hit]))
        name, i0, i1 = hit[0]
        if name == want:
            continue
        block = text[i0:i1]
        q0 = block.index('"')
        q1 = block.index('"', q0 + 1)
        edits.append((i0 + q0 + 1, i0 + q1, name, want, "rename"))
        renames += 1
        print("   %-4s pin %-3s (%.2f,%.2f)  %-8s -> %s"
              % (ref, num, x, y, name, want))
print("   %d label(s) renamed" % renames)

# --- splice -----------------------------------------------------------------
if DRY:
    print("\ndry run -- not writing")
    sys.exit(0)

out = text
for a, b, old, new, kind in sorted(edits, key=lambda e: -e[0]):
    if out[a:b] != text[a:b]:
        sys.exit("span %d..%d was disturbed by an earlier edit" % (a, b))
    out = out[:a] + new + out[b:]

_sexp.save(SCH, out)
print("\nwrote %s : %d -> %d byte(s)"
      % (SCH.rsplit("\\", 1)[-1], len(text), len(out)))

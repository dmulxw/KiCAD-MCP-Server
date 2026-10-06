"""Every ROW*/CSEL*/DRV_CASC* label with its position and angle.

Each of these should appear on a 595 output pin and, for the ones that reach the
panel connector, once more on J8/J10 -- except J8/J10 turned out to carry no
labels at all, so a second copy means an extra attachment nobody accounted for.
Find it before deleting anything.
"""
import re
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
text = _sexp.load(SCH)

want = re.compile(r"^(ROW\d+|CSEL\d+|DRV_CASC\d+)$")
rows = []
for head, i0, i1 in _sexp.children(text):
    if head != "label":
        continue
    b = text[i0:i1]
    nm = b.split('"')[1]
    if not want.match(nm):
        continue
    at = _sexp.find_at(b)
    rows.append((nm, at[0], at[1], at[2], i0, i1))


def num(nm):
    m = re.match(r"([A-Z_]+)(\d+)", nm)
    return (m.group(1), int(m.group(2)))


rows.sort(key=lambda r: (num(r[0]), r[1], r[2]))
print("net             x          y      ang   span")
for nm, x, y, a, i0, i1 in rows:
    print("%-12s %8.2f %9.2f  %4.0f   %d..%d" % (nm, x, y, a, i0, i1))

# Anything sharing a position with a ROW/CSEL label is a duplicate placement.
seen = {}
for nm, x, y, a, i0, i1 in rows:
    seen.setdefault((round(x, 2), round(y, 2)), []).append(nm)
dups = {k: v for k, v in seen.items() if len(v) > 1}
print("\npositions holding more than one label: %d" % len(dups))
for k, v in sorted(dups.items()):
    print("   %s : %s" % (k, v))

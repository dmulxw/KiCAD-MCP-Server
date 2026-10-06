"""Print raw label/wire blocks, so a new label can be written in the same shape.

Indentation, justification and the presence or absence of a trailing newline
all matter when splicing into a 228 KB file by hand.
"""
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
text = _sexp.load(SCH)
kids = _sexp.children(text)

by_name = {}
for head, i0, i1 in kids:
    if head == "label":
        nm = text[i0:i1].split('"')[1]
        by_name.setdefault(nm, []).append((i0, i1))

for nm in ("ROW0", "GND", "+3V3", "IO9", "DRV_CASC1"):
    if nm not in by_name:
        print("### %s : absent" % nm)
        continue
    i0, i1 = by_name[nm][0]
    print("### %s  (%d..%d)  x%d" % (nm, i0, i1, len(by_name[nm])))
    print(repr(text[i0 - 1:i1 + 1]))
    print()

for head, i0, i1 in kids:
    if head == "wire":
        print("### wire (%d..%d)" % (i0, i1))
        print(text[i0:i1])
        print("context:", repr(text[i0 - 20:i1 + 20]))
        break

print("\n### label counts")
for k in sorted(by_name):
    print("   %-10s %d" % (k, len(by_name[k])))

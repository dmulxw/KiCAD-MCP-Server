"""What actually sits on the right-hand side of the carrier sheet.

_sympins put J8/J10's pins at y=177.80 and y=193.04 and found nothing there,
so either the pin geometry or the rotation is off.  This prints the raw
evidence: Conn_01x20's library pin coordinates, and every label and symbol
east of x=170, which is where the two panel connectors live.
"""
import re
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
text = _sexp.load(SCH)
kids = _sexp.children(text)

libs = [text[i0:i1] for h, i0, i1 in kids if h == "lib_symbols"][0]
for name in ("Connector_Generic:Conn_01x20", "74xx:74HC595"):
    at = libs.find('(symbol "%s"' % name)
    print("--- %s at %d" % (name, at))
    if at < 0:
        continue
    # first 700 chars of the definition are enough to see the pin layout
    print(libs[at:at + 900])
    print()

print("=== labels with x > 170")
n = 0
for head, i0, i1 in kids:
    if head != "label":
        continue
    at = _sexp.find_at(text[i0:i1])
    if at and at[0] > 170:
        print("   %-8s at (%.2f, %.2f, %.0f)" % (text[i0:i1].split('"')[1],
                                                 at[0], at[1], at[2]))
        n += 1
print("   total %d" % n)

print("\n=== symbols with x > 170")
for head, i0, i1 in kids:
    if head != "symbol":
        continue
    b = text[i0:i1]
    at = _sexp.find_at(b)
    ref = re.search(r'\(property "Reference" "([^"]+)"', b)
    if at and at[0] > 170 and ref:
        print("   %-5s at (%.2f, %.2f, %.0f)" % (ref.group(1), at[0], at[1], at[2]))

print("\n=== no_connect")
for head, i0, i1 in kids:
    if head == "no_connect":
        print("   at %s" % (_sexp.find_at(text[i0:i1]),))

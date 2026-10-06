"""Compare the no_connect flags before and after the 595 removal.

Two of them now dangle, which deletion of the shift registers should not have
caused -- unless the splice swallowed one, or a flag was resting on a pin that
went away.
"""
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _geom
import _sexp

D = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
PAIR = [(D + r"\YD-ESP32-S3-Carrier.kicad_sch.pre-car595.bak", "before"),
        (D + r"\YD-ESP32-S3-Carrier.kicad_sch", "after ")]

for path, tag in PAIR:
    text = _sexp.load(path)
    ncs = []
    for head, i0, i1 in _sexp.children(text):
        if head == "no_connect":
            ncs.append(_sexp.find_at(text[i0:i1]))
    print("%s  %d byte(s), %d no_connect" % (tag, len(text), len(ncs)))
    for p in sorted(ncs, key=lambda t: (t[1], t[0])):
        print("     (%.4f, %.4f)" % (p[0], p[1]))
    print()

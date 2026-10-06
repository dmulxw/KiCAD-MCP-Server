"""Read J8/J10's own block, and Conn_01x20's pin definitions, verbatim.

Both connectors have 40 pins on the sheet and not one label between them, yet
ERC reports nothing.  Whatever explains that is in these two blocks, so print
them rather than reason about them.
"""
import re
import sys

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")
text = _sexp.load(SCH)
kids = _sexp.children(text)


def sub_block(t, start):
    d = 0
    s = e = False
    j = start
    while j < len(t):
        c = t[j]
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
                return t[start:j + 1]
        j += 1
    raise ValueError("unbalanced")


# --- the symbol instances
for head, i0, i1 in kids:
    if head != "symbol":
        continue
    b = text[i0:i1]
    m = re.search(r'\(property "Reference" "([^"]+)"', b)
    if m and m.group(1) in ("J8", "J10"):
        print("========== instance %s (%d..%d, %d bytes)"
              % (m.group(1), i0, i1, i1 - i0))
        print(b)
        print()

# --- the library definition's pins
libs = [text[i0:i1] for h, i0, i1 in kids if h == "lib_symbols"][0]
at = libs.find('(symbol "Connector_Generic:Conn_01x20"')
block = sub_block(libs, at)
print("========== Conn_01x20 definition: %d bytes" % len(block))
i = 0
seen = 0
while True:
    i = block.find("(pin ", i)
    if i < 0:
        break
    form = sub_block(block, i)
    print("   %s" % " ".join(form.split())[:150])
    seen += 1
    i += len(form)
print("   %d pin(s)" % seen)
print()
print("also present in the definition:",
      sorted(set(re.findall(r"\((pin_names|pin_numbers|offset|hide)\b", block))))
m = re.search(r"\(pin_names.*?\)\s*\)", block, re.S)
print("pin_names block:", " ".join(m.group(0).split()) if m else None)
m = re.search(r"\(pin_numbers[^)]*\)", block)
print("pin_numbers block:", " ".join(m.group(0).split()) if m else None)

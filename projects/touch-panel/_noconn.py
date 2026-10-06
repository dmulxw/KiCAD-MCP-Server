"""Mark pins that are deliberately unused.

The last chip in a cascade has one output left over and no successor to feed,
so U4's QH and QH' are genuinely empty.  An empty pin is an ERC error until it
is flagged, and flagging it is a two-line top-level form placed on the pin
endpoint.

  python _noconn.py X Y [X Y ...] [--sch PATH] [--dry-run]
"""
import sys
import uuid

sys.path.insert(0, r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel")
import _sexp

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_sch")
DRY = False
pts = []
i = 1
while i < len(sys.argv):
    a = sys.argv[i]
    if a == "--sch":
        SCH = sys.argv[i + 1]
        i += 2
    elif a == "--dry-run":
        DRY = True
        i += 1
    else:
        pts.append((float(a), float(sys.argv[i + 1])))
        i += 2

if not pts:
    sys.exit("usage: _noconn.py X Y [X Y ...] [--sch PATH] [--dry-run]")

text = _sexp.load(SCH)
existing = []
for head, i0, i1 in _sexp.children(text):
    if head == "no_connect":
        existing.append(_sexp.find_at(text[i0:i1]))
print("%d no_connect already on the sheet" % len(existing))

new = []
for x, y in pts:
    if any(e and abs(e[0] - x) < 0.01 and abs(e[1] - y) < 0.01 for e in existing):
        print("   (%.2f, %.2f) already flagged" % (x, y))
        continue
    new.append((x, y))

if not new:
    print("nothing to add")
    sys.exit(0)

for x, y in new:
    print("   flagging (%.2f, %.2f)" % (x, y))
if DRY:
    sys.exit(0)

# Top-level children go immediately before the root form's closing paren.
end = text.rstrip()
if not end.endswith(")"):
    sys.exit("root form does not close with ')' -- refusing to splice")
body = end[:-1].rstrip("\n")
add = "".join(
    '\n\t(no_connect\n\t\t(at %s %s)\n\t\t(uuid "%s")\n\t)'
    % (repr(x), repr(y), uuid.uuid4()) for x, y in new)
_sexp.save(SCH, body + add + "\n)\n")
print("wrote %s" % SCH.rsplit("\\", 1)[-1])

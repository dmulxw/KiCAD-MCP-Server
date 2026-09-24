"""Delete the no_connect flags that the v2 netlist has just replaced with labels.

KiCad only needs a no_connect on a pin that is *deliberately* left floating.  The
14 J1/J2 pins that used to be spare are now broken out to J6/J7/J9, so leaving the
X marks in place would put an ERC "connected but marked no-connect" error on each
one.  There is no MCP tool for removing a no_connect, so this edits the file text.

The schematic is CRLF with tab indentation, and the block is exactly:

    \\t(no_connect\\r\\n\\t\\t(at X Y)\\r\\n\\t\\t(uuid "...")\\r\\n\\t)\\r\\n

so the match is anchored on the whole block rather than on the coordinate alone --
a coordinate-only edit would leave an orphaned uuid behind.
"""
import re

SCH = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_sch")

# (x, y) of the flags that J6/J7/J9 have just taken over.
DROP = {
    (39.37, 46.99), (39.37, 49.53),            # J1 IO17, IO18   -> J9
    (39.37, 59.69), (39.37, 62.23),            # J1 IO9,  IO10   -> J6
    (39.37, 64.77), (39.37, 67.31),            # J1 IO11, IO12   -> J6
    (39.37, 69.85), (39.37, 72.39),            # J1 IO13, IO14   -> J6
    (90.17, 26.67), (90.17, 29.21),            # J2 IO43, IO44   -> J7
    (90.17, 36.83), (90.17, 44.45),            # J2 IO42, IO39   -> J7
    (90.17, 46.99), (90.17, 62.23),            # J2 IO38, IO48   -> J7
}

BLOCK = re.compile(
    r"\t\(no_connect\r\n"
    r"\t\t\(at ([-\d.eE+]+) ([-\d.eE+]+)\)\r\n"
    r"\t\t\(uuid \"[0-9a-f-]+\"\)\r\n"
    r"\t\)\r\n")

with open(SCH, "r", encoding="utf-8", newline="") as f:
    src = f.read()

before = len(BLOCK.findall(src))
kept, dropped = [], []


def repl(m):
    # KiCad writes 39.370000000000005 for 39.37, so an exact float compare finds
    # nothing -- compare at 0.01 mm, which is finer than any real schematic grid.
    key = (round(float(m.group(1)), 2), round(float(m.group(2)), 2))
    if key in DROP:
        dropped.append(key)
        return ""
    kept.append(key)
    return m.group(0)


out = BLOCK.sub(repl, src)

missing = DROP - set(dropped)
assert not missing, f"no no_connect found at {sorted(missing)}"
assert len(out) < len(src), "nothing was removed"

with open(SCH, "w", encoding="utf-8", newline="") as f:
    f.write(out)

print(f"no_connect flags: {before} -> {before - len(dropped)}  "
      f"(removed {len(dropped)})")
for x, y in sorted(dropped):
    print(f"  - ({x}, {y})")
print(f"still floating (kept): {len(kept)}")
for x, y in sorted(kept):
    print(f"  . ({x}, {y})")

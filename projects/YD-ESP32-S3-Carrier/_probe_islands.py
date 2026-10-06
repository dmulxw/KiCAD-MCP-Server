"""Find the GND pour islands that DRC calls unconnected, and where a via would
join them.

The DRC report names the offenders as `填充区[GND]在 F.Cu 上` vs `... 在 B.Cu 上`,
but a zone item's `pos` in the JSON is the zone outline origin (0.50, 0.50) --
the same number for every island on the board -- so the report cannot say where
they are.  So measure it directly: rasterise the *filled* copper of each GND zone
at 0.2 mm, flood-fill the connected components, and note which ones hold a GND
via or a through-hole GND pad.

A component with no via and no THT pad is walled in on its own layer; if the fill
did not discard it, it is there because it touches something, and the something
is on one side only.  Those are the islands to stitch -- and once you can see
them, the fix is a via inside the island rather than a denser global lattice.

  python _probe_islands.py [board.kicad_pcb]
"""
import sys

import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else (
    r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
    r"\_v90.kicad_pcb")

GRID = 0.20
BW, BH = 100.0, 74.0
NX = int(BW / GRID) + 1
NY = int(BH / GRID) + 1
FROM = pcbnew.FromMM


def cell(x, y):
    return int(round(x / GRID)), int(round(y / GRID))


board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)

TO = pcbnew.ToMM
gnd = None
for code, net in board.GetNetInfo().NetsByNetcode().items():
    if str(net.GetNetname()) == "GND":
        gnd = code
print("board", BOARD)
print("GND netcode", gnd)

# ---- rasterise the filled pour, one bytearray per layer -------------------
inside = {}
zones = {l: [z for z in board.Zones()
             if not z.GetIsRuleArea() and z.IsOnLayer(l)]
         for l in (pcbnew.F_Cu, pcbnew.B_Cu)}
for l, name in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
    buf = bytearray(NX * NY)
    for z in zones[l]:
        bb = z.GetBoundingBox()
        i0 = max(0, int(TO(bb.GetLeft()) / GRID))
        i1 = min(NX - 1, int(TO(bb.GetRight()) / GRID) + 1)
        j0 = max(0, int(TO(bb.GetTop()) / GRID))
        j1 = min(NY - 1, int(TO(bb.GetBottom()) / GRID) + 1)
        for i in range(i0, i1 + 1):
            x = i * GRID
            for j in range(j0, j1 + 1):
                if buf[j * NX + i]:
                    continue
                if z.HitTestFilledArea(l, pcbnew.VECTOR2I(FROM(x), FROM(j * GRID))):
                    buf[j * NX + i] = 1
    inside[l] = buf
    print("  %s: %d cell(s) of pour, %d zone(s)"
          % (name, sum(buf), len(zones[l])))

# ---- where the pour meets a GND via or a through GND pad ------------------
vias, pads = [], []
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND":
        p = t.GetPosition()
        vias.append((TO(p.x), TO(p.y)))
for fp in board.GetFootprints():
    for p in fp.Pads():
        if str(p.GetNetname()) != "GND":
            continue
        pos = p.GetPosition()
        thru = p.IsOnLayer(pcbnew.F_Cu) and p.IsOnLayer(pcbnew.B_Cu)
        pads.append((TO(pos.x), TO(pos.y), thru,
                     str(fp.GetReference()) + "." + str(p.GetNumber())))
print("  %d GND via(s), %d GND pad(s) (%d through)"
      % (len(vias), len(pads), sum(1 for q in pads if q[2])))

# ---- connected components, 4-connected ------------------------------------
comp = {}
for l in (pcbnew.F_Cu, pcbnew.B_Cu):
    buf = inside[l]
    ids = [-1] * (NX * NY)
    n = 0
    for start in range(NX * NY):
        if not buf[start] or ids[start] != -1:
            continue
        stack = [start]
        ids[start] = n
        size = 0
        x0 = x1 = start % NX
        y0 = y1 = start // NX
        while stack:
            c = stack.pop()
            size += 1
            i, j = c % NX, c // NX
            x0, x1 = min(x0, i), max(x1, i)
            y0, y1 = min(y0, j), max(y1, j)
            if i and buf[c - 1] and ids[c - 1] < 0:
                ids[c - 1] = n
                stack.append(c - 1)
            if i < NX - 1 and buf[c + 1] and ids[c + 1] < 0:
                ids[c + 1] = n
                stack.append(c + 1)
            if j and buf[c - NX] and ids[c - NX] < 0:
                ids[c - NX] = n
                stack.append(c - NX)
            if j < NY - 1 and buf[c + NX] and ids[c + NX] < 0:
                ids[c + NX] = n
                stack.append(c + NX)
        comp[(l, n)] = {"size": size, "vias": 0, "pads": 0, "thru": 0,
                        "who": [],
                        "bbox": (x0 * GRID, x1 * GRID, y0 * GRID, y1 * GRID)}
        n += 1
    inside[l] = (ids, n)
    print("  %s: %d component(s)" % ("F.Cu" if l == pcbnew.F_Cu else "B.Cu", n))

# ---- score each component, and note the layer-crossing points -------------
# A via ties the two layers at one point; so does a THT pad.  Those are the only
# places the two rasters can join, so they are what the union below runs on.
def comp_of(l, x, y):
    ids, n = inside[l]
    i, j = cell(x, y)
    if not (0 <= i < NX and 0 <= j < NY):
        return None
    # The point is a via centre, not a pour cell: probe a small disc around it.
    for r in (0, 1, 2):
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if abs(di) != r and abs(dj) != r:
                    continue
                ii, jj = i + di, j + dj
                if 0 <= ii < NX and 0 <= jj < NY and ids[jj * NX + ii] >= 0:
                    return ids[jj * NX + ii]
    return None


parent = {}


def find(a):
    while parent.get(a, a) != a:
        parent[a] = parent.get(parent[a], parent[a])
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra


for c in comp:
    parent[c] = c

for (x, y) in vias:
    for l in (pcbnew.F_Cu, pcbnew.B_Cu):
        c = comp_of(l, x, y)
        if c is not None:
            comp[(l, c)]["vias"] += 1

for (x, y, thru, who) in pads:
    got = []
    for l in (pcbnew.F_Cu, pcbnew.B_Cu):
        c = comp_of(l, x, y)
        if c is not None:
            comp[(l, c)]["pads"] += 1
            comp[(l, c)]["who"].append(who)
            got.append((l, c))
    if thru and len(got) == 2:
        for (l, c) in got:
            comp[(l, c)]["thru"] += 1
        union(got[0], got[1])

for (x, y) in vias:                       # a via is a crossing point too
    got = []
    for l in (pcbnew.F_Cu, pcbnew.B_Cu):
        c = comp_of(l, x, y)
        if c is not None:
            got.append((l, c))
    if len(got) == 2:
        union(got[0], got[1])

groups = {}
for c in comp:
    groups.setdefault(find(c), []).append(c)

print("\n=== %d electrical island(s) across both layers ===" % len(groups))
for root, members in sorted(groups.items(), key=lambda kv: -sum(
        comp[m]["size"] for m in kv[1])):
    size = sum(comp[m]["size"] for m in members) * GRID * GRID
    pads = sum(comp[m]["pads"] for m in members)
    vias = sum(comp[m]["vias"] for m in members)
    bx = [comp[m]["bbox"] for m in members]
    print("  %7.1f mm2  %2d piece(s) %2d pad(s) %3d via(s)   "
          "x %6.2f..%6.2f  y %6.2f..%6.2f"
          % (size, len(members), pads, vias,
             min(b[0] for b in bx), max(b[1] for b in bx),
             min(b[2] for b in bx), max(b[3] for b in bx)))

print("\n=== per-layer pieces with no via and no through pad ===")
for (l, n), d in sorted(comp.items(), key=lambda kv: -kv[1]["size"]):
    if d["vias"] or d["thru"]:
        continue
    print("  %-5s %7.1f mm2  %2d pad(s) %-24s x %6.2f..%6.2f  y %6.2f..%6.2f"
          % ("F.Cu" if l == pcbnew.F_Cu else "B.Cu", d["size"] * GRID * GRID,
             d["pads"], ",".join(d["who"][:4]),
             d["bbox"][0], d["bbox"][1], d["bbox"][2], d["bbox"][3]))

# ---- where a repair via would go ------------------------------------------
# A via ties a piece of pour to the pour on *the other layer*, at one point.
# So the useful spot is a cell inside a stranded island whose opposite-layer
# cell already belongs to the main island: one via there and the island is home.
# Anything else merely welds two stranded pieces together.
BASE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
sys.path.insert(0, BASE + r"\scripts")
import pour as P  # noqa: E402  (now importable: its main() is guarded)

main_root = max(groups, key=lambda r: sum(comp[m]["size"] for m in groups[r]))
print("\n=== repair via candidates (island -> main, %d via(s) needed at most) ==="
      % (len(groups) - 1))
for root, members in sorted(groups.items(),
                            key=lambda kv: -sum(comp[m]["size"] for m in kv[1])):
    if root == main_root:
        continue
    other = {pcbnew.F_Cu: pcbnew.B_Cu, pcbnew.B_Cu: pcbnew.F_Cu}
    found = []
    for (l, n) in members:
        if found:
            break
        ids, _ = inside[l]
        ox0, ox1, oy0, oy1 = comp[(l, n)]["bbox"]
        for i in range(int(ox0 / GRID), int(ox1 / GRID) + 1):
            if found:
                break
            for j in range(int(oy0 / GRID), int(oy1 / GRID) + 1):
                if ids[j * NX + i] != n:
                    continue
                o = other[l]
                oids, _ = inside[o]
                oc = oids[j * NX + i]
                if oc < 0 or find((o, oc)) != main_root:
                    continue
                x, y = i * GRID, j * GRID
                if not P.free_for_via(board, x, y):
                    continue
                # A via is legal here and the far side is already home.
                found.append((l, x, y))
                break
    if found:
        l, x, y = found[0]
        print("  %7.1f mm2 piece at x %6.2f..%6.2f y %6.2f..%6.2f  ->  via at "
              "(%6.2f,%6.2f)  %s -> %s"
              % (sum(comp[m]["size"] for m in members) * GRID * GRID,
                 comp[members[0]]["bbox"][0], comp[members[0]]["bbox"][1],
                 comp[members[0]]["bbox"][2], comp[members[0]]["bbox"][3],
                 x, y,
                 "F.Cu" if l == pcbnew.F_Cu else "B.Cu",
                 "B.Cu" if l == pcbnew.F_Cu else "F.Cu"))
    else:
        print("  %7.1f mm2 piece has NO direct spot -- needs a chained stitch"
              % (sum(comp[m]["size"] for m in members) * GRID * GRID))

"""Where the 595 control/power pins are, and what stands between them.

Half the board's unconnected items are NOT the R-column weave.  They are the
daisy-chains that were supposed to be created when the four 74HC595s moved from
the carrier onto this panel:

  +3V3   x12   C2.1 -> U3.10, VCC and /MR of all four
  IO10   x 4   U1.11 -> U2.11 -> U3.11 -> U4.11   (SRCLK)
  IO11   x 4   U1.12 -> U2.12 -> U3.12 -> U4.12   (RCLK)
  IO12   x 4   U1.13 -> U2.13 -> U3.13 -> U4.13   (/OE)
  IO9    x 1   U1.14 -> J1.1                      (DS)
  GND    x 8   dangling stubs

And the decisive evidence that this is a separate problem: in the lift test the
router never fixed a single one of them.  +3V3 stays 12, IO10/11/12 stay 4 each,
IO9 stays 1 -- before the lift and after it.  So they are not waiting on the
weave; they are waiting on their own corridor, which nobody has measured yet.

This measures it.  Pad-number -> signal on a 74HC595: 1-7 Q0-Q6, 8 GND, 9 Q7',
10 /MR, 11 SRCLK, 12 RCLK, 13 /OE, 14 DS, 15 Q7, 16 VCC.

  python _tp_595.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6

# every net that is part of the unconnected 595 group, and its expected chain
CHAINS = ["+3V3", "IO9", "IO10", "IO11", "IO12", "GND"]

board = pcbnew.LoadBoard(BOARD)

# ---- 1. the four shift registers: every pad, by number ---------------------
regs = {}
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    if not ref.startswith("U"):
        continue
    ps = {}
    for p in fp.Pads():
        q = p.GetBoundingBox()
        ps[str(p.GetNumber())] = (
            str(p.GetNetname()),
            (q.GetLeft() + q.GetRight()) / 2 / S,
            (q.GetTop() + q.GetBottom()) / 2 / S,
            q.GetLeft() / S, q.GetTop() / S, q.GetRight() / S, q.GetBottom() / S,
            p.GetPosition().x / S, p.GetPosition().y / S)
    if len(ps) >= 16:
        regs[ref] = ps

print("=== the shift registers ===")
for ref in sorted(regs, key=lambda r: int(r[1:])):
    ps = regs[ref]
    ys = [v[2] for v in ps.values()]
    xs = [v[1] for v in ps.values()]
    print("  %-4s  %d pads   x %.2f..%.2f   y %.2f..%.2f"
          % (ref, len(ps), min(xs), max(xs), min(ys), max(ys)))

# ---- 2. the daisy-chained pins, register by register -----------------------
print("\n=== the chained pins, in register order ===")
PINNAME = {"8": "GND", "10": "/MR", "11": "SRCLK", "12": "RCLK",
           "13": "/OE", "14": "DS", "15": "Q7", "16": "VCC"}
for num in ["8", "10", "11", "12", "13", "14", "15", "16"]:
    row = []
    for ref in sorted(regs, key=lambda r: int(r[1:])):
        p = regs[ref].get(num)
        if not p:
            continue
        row.append("%s (x%7.2f y%7.2f %s)" % (ref, p[1], p[2], p[0]))
    if row:
        print("  pad %-2s %-6s %s" % (num, PINNAME.get(num, "?"), "  ".join(row)))

# ---- 3. what actually connects each unconnected chain net today ------------
print("\n=== existing copper on each chain net ===")
for net in CHAINS:
    segs, vias = [], []
    for t in board.GetTracks():
        if str(t.GetNetname()) != net:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            q = t.GetPosition()
            vias.append((TO(q.x), TO(q.y)))
            continue
        s, e = t.GetStart(), t.GetEnd()
        segs.append((str(t.GetLayerName()), TO(s.x), TO(s.y), TO(e.x), TO(e.y)))
    pads = sum(1 for ref in regs for p in regs[ref].values() if p[0] == net)
    fl = defaultdict(int)
    for (l, _a, _b, _c, _d) in segs:
        fl[l] += 1
    print("  %-6s %2d pads on the registers, %3d track(s) %s, %2d via(s)"
          % (net, pads, len(segs), dict(fl), len(vias)))

# ---- 4. the corridor between registers, on the east (control) side ---------
print("\n=== east-side corridor: x span of control pins, and what crosses it ===")
east = {}
for ref in sorted(regs, key=lambda r: int(r[1:])):
    ys = [v[2] for n, v in regs[ref].items() if n in ("11", "12", "13", "14", "15", "16")]
    xs = [v[1] for n, v in regs[ref].items() if n in ("11", "12", "13", "14", "15", "16")]
    east[ref] = (min(xs), max(xs), min(ys), max(ys))
    print("  %-4s control pins x %.2f..%.2f  y %.2f..%.2f" % (ref, *east[ref]))

# for each vertical gap between consecutive registers, what copper is in it?
order = sorted(regs, key=lambda r: int(r[1:]))
XLO = min(v[0] for v in east.values()) - 2.0
XHI = max(v[1] for v in east.values()) + 4.0
print("\n  -- obstacles in the east corridor x %.2f..%.2f --" % (XLO, XHI))
for i in range(len(order) - 1):
    a, b = order[i], order[i + 1]
    y0, y1 = east[a][3], east[b][2]
    occ = defaultdict(int)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            q = t.GetPosition()
            x, y = TO(q.x), TO(q.y)
            if XLO <= x <= XHI and y0 - 0.6 <= y <= y1 + 0.6:
                occ["VIA:" + str(t.GetNetname())] += 1
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1s, x2, y2e = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
        if max(y1s, y2e) < y0 - 0.6 or min(y1s, y2e) > y1 + 0.6:
            continue
        if max(x1, x2) < XLO or min(x1, x2) > XHI:
            continue
        occ[str(t.GetLayerName())[:2] + ":" + str(t.GetNetname())] += 1
    print("     %s->%s  y %7.2f..%7.2f  %s"
          % (a, b, y0, y1,
             ", ".join("%s x%d" % kv for kv in sorted(occ.items())) or "CLEAR"))

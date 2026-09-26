"""Phase A: connect all 40 header pins to the copper their net already owns.

The board is _pins.kicad_pcb -- rip3's cleared board with the two headers netted.
DRC there reads 128 violations (53 of them the untouched silkscreen baseline)
and 117 unconnected items, and those 117 decompose exactly: 77 rip artifacts
plus 40 header pins.  So this script has one job and one measure of success:
40 pins connected, and the DRC number should fall as it goes.

Obstacles are "every copper item not on this net" -- which is what exempts the
source pad, since it is on this net.  Do NOT also exempt the other header's
pads: reach2/reach3 did that to answer a reachability question, but for routing
it would let a route cross straight over another net's pad and short it.  The
one thing that makes starts_near() work here is that the source pad's own net is
filtered out, so the nearest obstacle to a header pin is the neighbouring pin
1.69mm away, not the pin itself.

Order is deliberate.  ROW3 and ROW5 first, per the standing instruction to get
them out of their 3x2mm box ahead of everything else -- with the new assignment
they are also the two shortest hops on the board (5.1mm), so the instruction and
"easiest first" now agree.  Then the remaining ROUTES shortest-first, so the
cheap work is banked before the strip-only pockets claim the corridor they need.
"""
import sys, os, time
sys.path.insert(0, os.getcwd())
import pcbnew
import emitlib as M
import probe

S = 1e6
SRC = os.environ.get("SRC", "_pins.kicad_pcb")
OUT = os.environ.get("OUT", "_r1.kicad_pcb")
ONLY = set(sys.argv[1:])
# The plan specifies --step 0.05; every run so far used the 0.1 default.  keep
# and pad_keep do not scale with step, so a corridor that fits exactly one cell
# at 0.1 fits about four at 0.05 -- the between-pin channel (0.84mm against
# 2*0.34 keep = 0.68) is the one that matters here.
ST = float(os.environ.get("ST", "0.1"))

# (net, ref, pin) in the order they will be routed -- exactly the assignment
# pins.py wrote, sequenced.
#
# Run 1 was shortest-first and lost 8 pins, all on J1B, all at its bottom end:
# pins 13,14,15,16 each expanded exactly 864 cells (one shared pocket) and
# +3V3 on 17-20 exhausted 4.5M cells with a goal 3.00mm away.  Every J1A pin
# was fine.  The cause is per-header: J1B's pins 1-12 have y 180.97..208.91 and
# their routes fanned *downward* into the pocket holding pins 13-20.
#
# So J1B is now taken bottom-up -- each route leaves from the free end, and the
# pins that were sealed go first while the pocket is still open.  +3V3 pin 20
# leads its group because pins 17-19 then chain off the copper it lays down
# beside them (run 1 showed GNDA 17/18/19 costing 0.0/0.1/1.5mm once 16 routed).
TASKS = [
    ("ROW3", "J1A", 1), ("ROW5", "J1A", 20),          # standing instruction
    # ---- J1B, bottom-up ----
    ("+3V3", "J1B", 20), ("GND", "J1B", 16),
    ("CSEL9", "J1B", 15), ("CSEL8", "J1B", 14), ("CSEL7", "J1B", 13),
    ("CSEL6", "J1B", 12), ("CSEL5", "J1B", 11),
    ("CSEL2", "J1B", 10), ("CSEL1", "J1B", 9), ("CSEL0", "J1B", 8),
    ("ROW20", "J1B", 7), ("ROW19", "J1B", 6), ("ROW18", "J1B", 5),
    ("ROW15", "J1B", 4), ("ROW12", "J1B", 3), ("ROW11", "J1B", 2),
    ("ROW10", "J1B", 1),
    # ---- J1A, bottom-up ----
    ("GND", "J1A", 19), ("GND", "J1A", 16),
    ("CSEL3", "J1A", 15), ("CSEL4", "J1A", 14),
    ("ROW17", "J1A", 13), ("ROW16", "J1A", 12), ("ROW14", "J1A", 11),
    ("ROW13", "J1A", 10), ("ROW9", "J1A", 9), ("ROW8", "J1A", 8),
    ("ROW7", "J1A", 7), ("ROW6", "J1A", 6), ("ROW4", "J1A", 5),
    ("ROW2", "J1A", 4), ("ROW1", "J1A", 3), ("ROW0", "J1A", 2),
]

board = pcbnew.LoadBoard(SRC)
M.bind(board, st=ST)
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

# A fiducial is a 1.0mm pad inside a 2.0mm mask opening, and pad_keep is measured
# from the pad's COPPER edge -- 0.54mm.  So the grid believes there is 1.04mm of
# room around an MK pad when the mask opening extends to 1.00mm, and a route laid
# through that belief puts copper inside the fiducial's clear zone.  DRC calls it
# solder_mask_bridge; the camera calls it a fiducial that no longer works.
# Measured: exactly one GND track of 8.1mm through MK3 at (156.5, 106).
#
# Inflating the pad to the mask size for the duration of the run is a routing
# proxy, not a board edit: the sizes are restored before SaveBoard, so the
# fiducials are still 1.0mm/2.0mm in the output.
MKSAVE = []
for ref in ("MK1", "MK2", "MK3"):
    fp = fps.get(ref)
    if fp is None:
        continue
    for p in fp.Pads():
        MKSAVE.append((p, p.GetSize()))
        p.SetSize(pcbnew.VECTOR2I(int(2.0 * S), int(2.0 * S)))
if MKSAVE:
    print("inflated %d fiducial pad(s) to their 2.0mm mask size for routing" % len(MKSAVE))
print("board %s: %d track(s), %d footprint(s)  step %.2f keep %.3f pad_keep %.3f"
      % (SRC, len(list(board.GetTracks())), len(list(board.GetFootprints())),
         M.step, M.keep, M.pad_keep), flush=True)

results = {}
t_all = time.time()
for netname, ref, pin in TASKS:
    if ONLY and ("%s.%d" % (ref, pin)) not in ONLY and netname not in ONLY:
        continue
    t0 = time.time()
    obstacles = [it for it in M.fresh() if it.GetNetname() != netname]
    g = M.make_grid(obstacles)
    mine = M.netcopper(netname)
    goals = M.goals_of(g, mine)
    src = fps[ref].FindPadByNumber(str(pin))
    c = src.GetPosition()
    tag = "%s %s.%-2d" % (netname, ref, pin)
    if not goals:
        print("   %-13s no goal cell  <-- net owns no copper" % tag, flush=True)
        results[(netname, ref, pin)] = "nog"
        continue
    ci, cj = g.ij(c.x/S, c.y/S)
    st = M.starts_near(g, src, r=20) or [(M.LAYERS[0], ci, cj)]
    path, cross, exp, closest = probe.astar(g, st, goals, 25.0, conflict=False)
    if path is None:
        print("   %-13s NO PATH  expanded %d  closest %.2fmm  %.0fs"
              % (tag, exp, closest[0]*M.step, time.time()-t0), flush=True)
        results[(netname, ref, pin)] = "none"
        continue
    ln = sum(((path[k][1]-path[k-1][1])**2
              + (path[k][2]-path[k-1][2])**2)**0.5
             for k in range(1, len(path))) * M.step
    pre = (c.x/S, c.y/S, path[0][0])
    p = g.xy(path[-1][1], path[-1][2])
    post = M.attach_pt(p[0], p[1], mine)
    post = None if post is None else (post[0], post[1], path[-1][0])
    nt, nv, nr = M.emit(netname, g, path, pre=pre, post=post)
    print("   %-13s %6.1fmm  %3d trk %2d via %2d run  %4.0fs"
          % (tag, ln, nt, nv, nr, time.time()-t0), flush=True)
    results[(netname, ref, pin)] = "ok"

for p, sz in MKSAVE:
    p.SetSize(sz)
if MKSAVE:
    print("restored %d fiducial pad(s)" % len(MKSAVE))
pcbnew.SaveBoard(OUT, board)
ok = sum(1 for v in results.values() if v == "ok")
fails = [k for k, v in results.items() if v != "ok"]
print("\n%d/%d pin(s) routed" % (ok, len(results)), flush=True)
if fails:
    print("failed: %s" % ", ".join("%s %s.%s" % k for k in fails), flush=True)
print("saved to %s   total %.1f min" % (OUT, (time.time()-t_all)/60.0), flush=True)

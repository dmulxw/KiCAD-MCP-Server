"""Derive _tp_route.py from the carrier's route.py, changing only the header.

The router body is a tuned A* maze router with rip-up; nothing in it is
carrier-specific except the board it opens and the origin its grid is pinned
to.  astar()'s heuristic is computed purely in grid indices, so it needs no
offset; only gi/gj/mx/my and edge_mask() convert between mm and cells.
"""
import io
import re

SRC = (r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\scripts\route.py")
DST = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\_tp_route.py")

s = io.open(SRC, encoding="utf-8", newline="").read()


def sub(old, new, want=1):
    global s
    n = s.count(old)
    assert n == want, (n, want, old[:80])
    s = s.replace(old, new)


# --- 1. the board the router opens -----------------------------------------
sub(r'projects\YD-ESP32-S3-Carrier"', r'projects\touch-panel"')
sub(r'r"\YD-ESP32-S3-Carrier.kicad_pcb")', r'r"\touch-panel.kicad_pcb")')

# --- 2. board size and the panel's non-zero origin --------------------------
sub("BOARD_W, BOARD_H = 100.0, 74.0",
    "# The panel's outline does not start at the origin: it spans x 89.95..181.05,\n"
    "# y 99.95..250.05.  The grid is pinned to that corner, so every mm<->cell\n"
    "# conversion carries the offset.\n"
    "BOARD_W, BOARD_H = 91.1, 150.1\n"
    "OX, OY = 89.95, 99.95")

# --- 3. mm <-> cell, in both directions ------------------------------------
sub("def gi(x):\n    return min(NX - 1, max(0, int(round(x / GRID))))",
    "def gi(x):\n    return min(NX - 1, max(0, int(round((x - OX) / GRID))))")
sub("def gj(y):\n    return min(NY - 1, max(0, int(round(y / GRID))))",
    "def gj(y):\n    return min(NY - 1, max(0, int(round((y - OY) / GRID))))")
sub("def mx(i):\n    return i * GRID", "def mx(i):\n    return OX + i * GRID")
sub("def my(j):\n    return j * GRID", "def my(j):\n    return OY + j * GRID")

# --- 4. the edge keepout is compared against real board mm -----------------
# The grid stays LOCAL: cell i is the millimetre OX + i*GRID.  gi/mx convert at
# the boundary and nothing else should care.  But the rasterizers sample the grid
# with `np.arange(i0, i1) * GRID` and compare those samples against shape
# coordinates taken straight off pcbnew -- absolute.  On the carrier the two
# coincided because OX was 0; here the difference is 89.95 mm, so every sampled
# distance came out ~90 mm too large, `d <= r` was never true, and nothing was
# ever rasterized.  Every obstacle mask came out empty, blocked_for() returned
# wide-open space, and route_net() laid nothing at all.
#
# `np.arange(i0, i1)` / `np.arange(j0, j1)` appear only in the five raster
# functions, so this is safe to apply globally.  edge_mask() uses np.arange(NX)
# and is deliberately untouched: it works in local mm and must keep doing so --
# comparing OX-shifted mm against BOARD_W would mark the whole board out of
# bounds, which is exactly the bug this replaced.
sub("(np.arange(i0, i1) * GRID)", "(OX + np.arange(i0, i1) * GRID)", want=5)
sub("(np.arange(j0, j1) * GRID)", "(OY + np.arange(j0, j1) * GRID)", want=5)

# --- 4b. clearance and via size have to be overridable ---------------------
#
# Both are hardcoded in the carrier's route.py and both are wrong for this board
# in the same direction: the router asks for *less* than the fab allows, so what
# it produces can be un-manufacturable while still "routing".
#
#   CLEAR   0.16 against the panel's own m_MinClearance of 0.200.  main() writes
#           the 0.16 straight back into the board's design settings, so the saved
#           file declares a laxer rule than the one it was designed to -- DRC
#           then passes a board the fab will reject.  The router must be run at
#           0.20 at minimum, and the rule must not be lowered to match it.
#   VIA_D   measured correct (all 529 board vias are 0.600/0.300 and that is the
#           board minimum), but kept overridable so the claim stays testable.
sub("CLEAR = 0.16          # copper-to-copper clearance, mm",
    "CLEAR = float(os.environ.get(\"CLEAR\", \"0.16\"))   # copper-to-copper, mm")

# The rule must never be lowered to match the router.  main() wrote CLEAR
# straight into m_MinClearance and then saved, so a CLEAR of 0.16 against this
# board's declared 0.200 produced a file that *declared* 0.16 -- DRC would then
# pass copper the fab rejects, and the discrepancy is invisible because the
# board's own rule was edited to agree with it.  Taking the max keeps the
# stricter of the two, so anything the router laid too close is reported instead
# of blessed.
sub("    ds.m_MinClearance = pcbnew.FromMM(CLEAR)",
    "    # Never relax the fab rule to match the router; keep whichever is stricter.\n"
    "    _declared = pcbnew.ToMM(ds.m_MinClearance)\n"
    "    ds.m_MinClearance = pcbnew.FromMM(max(_declared, CLEAR))\n"
    "    print(\"clearance rule %.3f mm (board declared %.3f, router wants %.3f)\"\n"
    "          % (max(_declared, CLEAR), _declared, CLEAR))")

# A wider via needs a wider keepout, so VIA_D and CLEAR move together: the via
# mask is built at CLEAR + VIA_D/2 and the drill must stay inside the pad.
sub("VIA_D, VIA_DRILL = 0.60, 0.30",
    "VIA_D = float(os.environ.get(\"VIA_D\", \"0.60\"))\n"
    "VIA_DRILL = float(os.environ.get(\"VIA_DRILL\", \"0.30\"))")

# --- 5. no via bans: the carrier's two are mechanical (audio module, USB
#        shell) and neither part exists on the panel -------------------------
s = re.sub(r"^VIA_BAN = \[.*?\]$", "VIA_BAN = []", s, count=1, flags=re.M)
assert "VIA_BAN = []" in s

sub('WIDTHS = {"+5V": 1.00, "VBAT": 1.00, "VBAT_SW": 0.60, '
    '"SW_NODE": 0.60, "+3V3": 0.80}',
    '# The panel is an FPC sensor board, not a power board: nothing here carries\n'
    '# more than the four 595s, so 0.30 mm everywhere and a slightly heavier rail.\n'
    '# The corridor the 595s sit in leaves ~1.0 mm per side of a 7.0 mm courtyard,\n'
    '# so a wider +3V3 would close the fan-out off entirely.\n'
    'WIDTHS = {"+3V3": 0.50}')

# --- 6. the nets that gain a pad -------------------------------------------
sub('"DRV_CASC1", "DRV_CASC2", "DRV_CASC3",\n     "+3V3", "IO9", "IO10", "IO11", "IO12"]',
    '"DRV_CASC1", "DRV_CASC2", "DRV_CASC3",\n'
    '     "+3V3", "GND", "IO9", "IO10", "IO11", "IO12"]')

sub('ROUNDS = int(os.environ.get("ROUNDS", "4"))',
    'ROUNDS = int(os.environ.get("ROUNDS", "8"))')

# GND is normally filtered out of `todo` by name; here it is one of the nets
# that genuinely gains pads, so it has to be allowed through.
sub('todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]',
    'todo = [n for n in router.pads if len(router.pads[n]) > 1]')

# --- 7. route_net(): A*'s goal has to be the pad-0 tree, not all the copper
#
# `taken[]` already asks the right question -- is this pad on copper reachable
# from pad 0 -- but A* was still handed `conn`, the raw mask of *every* piece of
# the net's copper.  On this board a net is several unjoined islands (only some
# of which the tree touches), so a pad sitting on a foreign island is already
# inside the goal set: A* returns a one-cell path, emit() lays no copper, the
# pad is marked done, and route_net() reports the net routed.  Measured on
# ROW0: `[OK ] ROW0 w=0.30 0 segs 0 via(s)` with the board's track count
# unchanged -- an empty success.
sub("""        reach = reachable(conn, [(i, j, l) for l in (pads[0][3] or (0, 1))
                                 for (i, j) in pads[0][2]])
        taken = [False] * len(pads)
        for a, (_, _, nodes, layers) in enumerate(pads):
            taken[a] = a == 0 or any(reach[l, i, j] and near[l, i, j]
                                     for l in (layers or (0, 1))
                                     for (i, j) in nodes)
        done = sum(taken)""",
    """        def seed():
            return [(i, j, l) for l in (pads[0][3] or (0, 1))
                    for (i, j) in pads[0][2]]

        def on_tree(mask):
            # A pad counts as done only when it sits on copper the tree can
            # reach.  Bare proximity to the net's copper is not the same
            # question: this board's nets are several unjoined islands, and a
            # pad on an island with no path back to pad 0 would be written off
            # as already connected.
            return [b == 0 or any(mask[l, i, j] and near[l, i, j]
                                  for l in (pads[b][3] or (0, 1))
                                  for (i, j) in pads[b][2])
                    for b in range(len(pads))]

        reach = reachable(conn, seed())
        taken = on_tree(reach)
        done = sum(taken)""")

sub("            path = self.astar(blocked, via_blocked, starts, conn, crowd=field)",
    """            # The goal is `reach` -- the copper joined to pad 0 -- and not
            # `conn`.  See the note above on taken[]: handing A* the whole
            # copper mask lets it "reach" an island that has nothing to do with
            # the tree and stop there, laying no copper at all.
            path = self.astar(blocked, via_blocked, starts, reach, crowd=field)""")

sub("""            self.emit(net, path, w, blocked, via_blocked, hw)
            taken[a] = True
            done += 1

            # widen the tree so the next pad can hook onto this trace too.  The
            # trace carries through its own layer; the pad copper it terminates on
            # carries through every layer that pad has.
            for (pi, pj, pl) in path:
                conn[pl, pi, pj] = True
            land(pads[a], conn)
        return True""",
    """            self.emit(net, path, w, blocked, via_blocked, hw)

            # widen the tree so the next pad can hook onto this trace too.  The
            # trace carries through its own layer; the pad copper it terminates on
            # carries through every layer that pad has.
            for (pi, pj, pl) in path:
                conn[pl, pi, pj] = True
            land(pads[a], conn)

            # Recompute the set instead of just setting taken[a].  A live tree
            # on this board tends to swallow a pre-routed island whole: the new
            # trace lands on one pad of an already-wired row and the rest of
            # that row comes along through copper that was already there.
            # Leaving those untaken would send the loop back for a redundant
            # trace to each of them.  taken[] only ever grows and taken[a] is
            # forced below, so `done` strictly increases and this still ends.
            reach = reachable(conn, seed())
            fresh = on_tree(reach)
            for b in range(len(pads)):
                if fresh[b]:
                    taken[b] = True
            # `near` is the net's *frozen* copper opened up by half a grid
            # step, so it cannot see the trace just emitted; without this a pad
            # the trace landed on would look untaken, be picked again, and A*
            # would return the same one-cell path forever.
            taken[a] = True
            done = sum(taken)
        return True""")

# --- 8. reachable() has to agree with astar() about what "connected" means --
#
# Two mismatches, both measured on ROW0 rather than reasoned about.
#
# (a) astar() moves 8-connected -- DIRS carries the four diagonals -- while
#     reachable() only walked the four orthogonal neighbours.  A path that
#     steps diagonally, which A* does constantly over open copper, is not a
#     4-connected chain: the cells touch corner to corner, the flood refuses to
#     step between them, and it stops dead at the first diagonal.  Two grid
#     cells meeting corner to corner at 0.2 mm are merged copper for a 0.30 mm
#     run, so 8-connectivity is also the physically honest model.
# (b) reachable() stayed within one layer, but a via is exactly how this board's
#     copper crosses sides.  With (a) fixed but not (b), conn grew 1615 -> 3403
#     cells as five traces were emitted into it while reachable(conn, pad 0)
#     returned 176 cells every time: the F.Cu stub around the chip pad, because
#     the traces themselves had been routed on B.Cu.  The A* goal stayed a small
#     pocket at the chip instead of becoming the row, so all twelve row pads
#     were routed one at a time and the fifth trace walled the sixth pad off
#     ("cannot reach pad (124.96, 110.05)", with a flood confirming 0 of the
#     176 goal cells were reachable from it).
#
# With both fixed the first trace reaches the row's pre-existing copper, every
# other pad on the row is on_tree(), and the row costs one trace, not thirteen.
sub("def reachable(mask, starts):\n"
    '    """Which cells of `mask` are 4-connected to any of `starts`, per layer.',
    "def reachable(mask, starts, via=None):\n"
    '    """Which cells of `mask` are connected to any of `starts`.')

sub("""    while stack:
        l, i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if not (0 <= i2 < NX and 0 <= j2 < NY):
                continue
            if mask[l, i2, j2] and not seen[l, i2, j2]:
                seen[l, i2, j2] = True
                stack.append((l, i2, j2))
    return seen""",
    """    # The eight moves astar() uses, so a diagonal run is one piece of copper
    # rather than two that merely touch.
    while stack:
        l, i, j = stack.pop()
        nb = [(l, i + di, j + dj) for di, dj in
              ((1, 0), (-1, 0), (0, 1), (0, -1),
               (1, 1), (1, -1), (-1, 1), (-1, -1))]
        if via is not None and via(mx(i), my(j)):
            # A via barrel joins the two sides.  Staying within one layer would
            # split every trace that crosses over into two pieces of copper.
            nb.append((1 - l, i, j))
        for (l2, i2, j2) in nb:
            if not (0 <= i2 < NX and 0 <= j2 < NY):
                continue
            if mask[l2, i2, j2] and not seen[l2, i2, j2]:
                seen[l2, i2, j2] = True
                stack.append((l2, i2, j2))
    return seen""")

# The deeper occurrence is written first: an 8-space pattern is a substring of
# the 12-space one, so substituting the shallow form first would rewrite both.
sub("            reach = reachable(conn, seed())",
    "            reach = reachable(conn, seed(), self.via_ok)")
sub("        reach = reachable(conn, seed())",
    "        reach = reachable(conn, seed(), self.via_ok)")

# --- 9. RIPPABLE: let the router move the board's own copper ----------------
#
# absorb() files every pre-existing track as `frozen`, and Router.__init__ is
# explicit that frozen copper is never a rip-up victim.  On the carrier that was
# right: HEAD's routing there was verified-good and only needed the new nets
# threaded past it.  On the panel it is the whole problem.  The nets that will
# not route -- CSEL3/5/6 reach a transistor at the top of the board, a header pin
# and the 595 at the bottom-left, spans of 143-160 mm -- fail because no legal
# 0.6 mm via site is left anywhere along them.  A via needs VIA_D/2 + clearance
# = 0.50 mm and the router only asks 0.46, so there is nothing to loosen; the
# copper has to move, and only rip-up moves it.
#
# Measured before writing this: GND is 297 of 2,410 segments, yet deleting it
# flips CSEL0 from None to routed and takes the pass from 23/40 to 26/39, and
# every remaining failure is a pad with blocked=0 whose A* succeeds the moment
# the via gate is zeroed.  That is a shape no mask tweak reaches.
#
# Safe to round-trip here because the panel has no arcs and no footprint-owned
# copper: all 2,939 items are plain PCB_TRACK / PCB_VIA, so write_back()'s
# (x1,y1,x2,y2,w) reproduction is exact.  main() therefore clears the originals
# before writing, or every track would land on the board twice.
sub('ROUNDS = int(os.environ.get("ROUNDS", "8"))',
    '\n'
    '# Off by default: freeze HEAD\'s copper exactly as the carrier does.  Set\n'
    '# RIPPABLE=1 to file it as rip-up-able instead, which is what the panel needs.\n'
    'RIPPABLE = bool(os.environ.get("RIPPABLE"))\n'
    'ROUNDS = int(os.environ.get("ROUNDS", "8"))')

# The "kept ... untouched" line is a lie once RIPPABLE is on -- nothing is kept
# and nothing is untouched -- and this is the one line the pass prints about the
# board's own copper, so it has to say which mode it ran in.
sub('''        print(f"kept {len(router.frozen)} track(s) / {len(router.frozen_vias)} "
              f"via(s) already on the board, untouched; "
              f"{len(ONLY)} net(s) may gain copper")''',
    '''        if RIPPABLE:
            print(f"adopted {len(router.tracks)} track(s) / {len(router.vias)} "
                  f"via(s) already on the board as rip-up-able; "
                  f"{len(ONLY)} net(s) may gain copper")
        else:
            print(f"kept {len(router.frozen)} track(s) / {len(router.frozen_vias)} "
                  f"via(s) already on the board, untouched; "
                  f"{len(ONLY)} net(s) may gain copper")''')

sub('''    them: they belong to the footprint, and U1's thermal vias are not ours to move.
    """
    for t in list(board.GetTracks()):''',
    '''    them: they belong to the footprint, and U1's thermal vias are not ours to move.

    With RIPPABLE set, "frozen" is the wrong word for any of it: the panel is
    being re-routed anyway (four chips have just been added to it), so its copper
    goes into `tracks` where rip() can reach it.  Same geometry, same masking --
    blocked_for() reads `tracks + frozen` -- but now movable.
    """
    dest = router.tracks if RIPPABLE else router.frozen
    dest_v = router.vias if RIPPABLE else router.frozen_vias
    for t in list(board.GetTracks()):''')

sub('''        if t.GetClass() == "PCB_VIA":
            router.frozen_vias.append((net, x1, y1))
        elif t.GetLayer() == pcbnew.F_Cu:
            router.frozen.append((net, 0, x1, y1, x2, y2,
                                  pcbnew.ToMM(t.GetWidth())))
        elif t.GetLayer() == pcbnew.B_Cu:
            router.frozen.append((net, 1, x1, y1, x2, y2,
                                  pcbnew.ToMM(t.GetWidth())))''',
    '''        if t.GetClass() == "PCB_VIA":
            dest_v.append((net, x1, y1))
        elif t.GetLayer() == pcbnew.F_Cu:
            dest.append((net, 0, x1, y1, x2, y2, pcbnew.ToMM(t.GetWidth())))
        elif t.GetLayer() == pcbnew.B_Cu:
            dest.append((net, 1, x1, y1, x2, y2, pcbnew.ToMM(t.GetWidth())))''')

sub('''    write_back(board, router)
    board.Save(BOARD)''',
    '''    if RIPPABLE:
        # Every track on the board is already in router.tracks, so writing them
        # back without clearing first would double each one.  clear_routing()
        # hands back the proxies it removed: they must stay referenced until the
        # save below, because destroying them while the board is still live
        # corrupts SWIG's object table and the next GetFootprints() returns raw
        # SwigPyObjects.
        _keep_alive = clear_routing(board)   # noqa: F841
    write_back(board, router)
    board.Save(BOARD)''')

io.open(DST, "w", encoding="utf-8", newline="").write(s)
print("wrote %s (%d lines)" % (DST, s.count("\n")))

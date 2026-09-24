"""Flood GND over both copper layers, then stitch the islands together.

GND is never routed -- route.py deliberately skips it and leaves all 20 GND pads
to the pour.  A pour alone is not enough on a board this busy though: the signal
traces slice F.Cu into islands, so a pad can end up on a fragment that never
reaches the rest of the net.  The fix is a field of GND stitching vias, which
tie the F.Cu and B.Cu pours together wherever both are present.

Order matters.  Vias go in *before* the fill: a via placed afterwards has to
fight the copper that has already been poured around it, whereas a via present
at fill time is simply the same net as the zone and gets connected to it.

The script is re-runnable -- it deletes every zone on the board first.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/pour.py
"""
import math

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 64.0

# 0.20 rather than route.py's 0.16: the pour is a plane, and its edge is the one
# place a short would matter most, so it keeps a little margin over the trace the
# board is held to.  Still under 8 mil, so it costs nothing at the fab, and it is
# tight enough that the filler can still get into the pockets between the header
# rows -- which is where the plane earns its keep on a board this busy.
CLEAR = 0.20          # zone-to-foreign-copper clearance, mm
MIN_W = 0.25          # minimum poured width
EDGE_INSET = 0.50     # zone outline inset from the board edge
THERMAL_GAP = 0.30
THERMAL_SPOKE = 0.40

# The screw holes are inset 4.5 mm, halfway between the 3 mm that would leave the
# hole flush against the corner and the 5 mm that would put H3's keepout into the
# J1 silkscreen.  2.70 keeps copper 1.10 mm clear of the hole edge now that the
# hole is Ø3.2 rather than Ø3.0.
HOLE_KEEPOUT = 2.70   # "no copper pour" radius around each M3 screw hole
HOLES = [(4.5, 4.5), (95.5, 4.5), (4.5, 59.5), (95.5, 59.5)]

STITCH_D = 0.60       # stitching via diameter
STITCH_DRILL = 0.30
STITCH_PITCH = 4.0    # candidate lattice, mm
STITCH_EDGE = 1.20    # keep stitching vias this far inside the board edge
STITCH_CLEAR = 0.25   # required air gap from any foreign copper

# Two boxes that must stay dead flat, so not even a Ø0.6 via goes in them:
#   - the ES8311 module lies flat on the board here;
#   - the dev board's USB socket sits over this band.  v1 hung it off the board
#     edge; at 64 mm tall the board stops level with the socket, so the socket now
#     overhangs a strip that is still inside the outline and the plug's overmould
#     passes over it.  Nothing gets to stick up in the way.
VIA_BAN = [(43.0, 11.0, 74.0, 32.0), (18.0, 60.0, 29.0, 64.0)]

# GND returns that get a solid connection instead of a thermal relief.
#
# A thermal relief is four deliberate inductors between a pad and the plane --
# right for a pad you have to hand-solder, backwards for a filter cap, whose
# entire job is a low-inductance path to ground.  It is also what DRC caught
# here: C1 pad 2 sits in a pocket of F.Cu pinched between its own pad 1, the
# I2S_BCK trace at x=42.672 and the +5V diagonal, and the one sliver that fitted
# (0.6 mm2 at x 43.2..44.0, y 41.2..42.2) could reach the net only through that
# single spoke -- starved_thermal, with the sliver's copper left dead.
#
# v2's power section gets the same treatment, for the same reason plus one more:
# C5-C8 are the boost converter's input and output reservoirs, so their ground
# return carries the switching current, and U1's exposed pad is both the charger's
# thermal path and its ground.  A thermal relief there would put four inductors
# in the loop and cut the pad's heatsinking to a quarter.
#
# Pads are matched by number and skipped silently if the number is wrong, so
# main() prints what actually matched -- an entry that does not appear there is a
# typo, not a no-op.
#
# U1 pad 1 and J7 pad 2 joined the list after DRC reported one starved spoke
# each: U1.1 is TEMP, strapped to GND on a pad that shares a corner with the
# exposed pad, and J7.2 is a spare-IO header's GND pin whose one remaining
# spoke was the only thing still touching the plane.
SOLID_GND = [("C1", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"),
             ("C5", "2"), ("C6", "2"), ("C7", "2"), ("C8", "2"),
             ("U1", "9"), ("U1", "1"), ("J7", "2")]


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0.0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def gnd_netcode(board):
    for code, net in board.GetNetInfo().NetsByNetcode().items():
        if net.GetNetname() == "GND":
            return code
    raise SystemExit("no GND net on this board")


# --------------------------------------------------------------------- zones
def drop_zones(board):
    """Strip every zone, so the script is re-runnable.

    The removed proxies are returned, not dropped -- destroying a SWIG proxy
    while the board is still live corrupts the binding (see route.clear_routing).
    """
    doomed = list(board.Zones())
    for z in doomed:
        board.Remove(z)
    return doomed


def rect_zone(board, layer, netcode, x0, y0, x1, y1):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(netcode)
    z.SetLocalClearance(pcbnew.FromMM(CLEAR))
    z.SetMinThickness(pcbnew.FromMM(MIN_W))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    for setter, mm in (("SetThermalReliefGap", THERMAL_GAP),
                       ("SetThermalReliefSpokeWidth", THERMAL_SPOKE)):
        try:
            getattr(z, setter)(pcbnew.FromMM(mm))
        except AttributeError:
            pass
    o = z.Outline()
    o.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(z)
    return z


def solid_gnd(board):
    """Give the filter caps' ground returns a solid connection to the pour.

    Has to run before the fill: the connection style is an input to the filler,
    not something you can retrofit onto copper that has already been poured.
    """
    done = []
    for ref, num in SOLID_GND:
        fp = board.FindFootprintByReference(ref)
        for p in fp.Pads():
            if str(p.GetNumber()) == num and p.GetNetname() == "GND":
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
                done.append(f"{ref}.{num}")
    # U1's SOIC-8-1EP splits its exposed pad into a 3x3 grid of nine pads all
    # numbered 9, so the list comes back with nine identical entries.  Report it
    # once -- nine copies of "U1.9" reads as a bug rather than as a match.
    return list(dict.fromkeys(done))


def hole_keepout(board, cx, cy, r):
    """A rule area that forbids copper pour around an M3 screw hole.

    An NPTH pad has no copper for the filler to respect, so without this the
    pour would close to within CLEAR of the hole edge -- far too close once a
    screw head and its washer are sitting on it.
    """
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    # A rule area arrives with several prohibitions on by default, including
    # pads -- which flags the mounting hole's own NPTH pad as a violation.
    # Clear them all, then forbid only the pour.
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowZoneFills(True)   # KiCad 10 name; pre-10 called this CopperPour
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)):
        o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(z)
    return z


# ------------------------------------------------------------------ stitching
def banned(x, y):
    if not (STITCH_EDGE <= x <= BOARD_W - STITCH_EDGE
            and STITCH_EDGE <= y <= BOARD_H - STITCH_EDGE):
        return True
    for (x0, y0, x1, y1) in VIA_BAN:
        if x0 - 1.0 <= x <= x1 + 1.0 and y0 - 1.0 <= y <= y1 + 1.0:
            return True
    for (hx, hy) in HOLES:
        # The keepout is a *square* of half-width HOLE_KEEPOUT, so the test has
        # to be Chebyshev, not Euclidean.  On the diagonal the two disagree by
        # up to sqrt(2): a via at (93.20, 57.20) is 3.25 mm from H4 -- outside a
        # 3.20 mm circle, so the old test passed it -- but only 2.30 mm away on
        # each axis, which puts it well inside the rule area, with no pour
        # under it on either layer and a dangling via at DRC.
        if max(abs(x - hx), abs(y - hy)) < HOLE_KEEPOUT + 0.5:
            return True
    return False


def free_for_via(board, x, y):
    """True when a ØSTITCH_D via centred here clears every pad and trace."""
    r = STITCH_D / 2.0 + STITCH_CLEAR
    pos = vec(x, y)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.HitTest(pos, pcbnew.FromMM(r)):
                return False
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            cx, cy = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
            # PCB_VIA::GetWidth() is per-layer; the no-arg form asserts
            if math.hypot(cx - x, cy - y) < pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2.0 + r:
                return False
            continue
        s, e = t.GetStart(), t.GetEnd()
        d = seg_dist(x, y, pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                     pcbnew.ToMM(e.x), pcbnew.ToMM(e.y))
        if d < pcbnew.ToMM(t.GetWidth()) / 2.0 + r:
            return False
    return True


def drop_stitch_vias(board):
    """Remove the previous run's stitching vias.

    route.py never places a GND via -- it skips the net entirely -- so every
    GND via on the board is ours.  Same SWIG caveat as drop_zones(): hand the
    proxies back rather than letting them die under a live board.
    """
    doomed = [t for t in board.GetTracks()
              if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    for v in doomed:
        board.Remove(v)
    return doomed


def fill_zones(board, layer):
    """The zones that actually carry copper on `layer`.

    Rule areas are excluded, not filtered later: GetFilledPolysList() asserts on
    one and wedges the whole process, so nothing here may reach them.

    IsOnLayer asks the question directly.  The obvious `LSET(layer)` intersection
    does not work -- LSET has no constructor from a bare PCB_LAYER_ID -- and a
    zone spans one layer anyway, so there is nothing an intersection would add.
    """
    return [z for z in board.Zones()
            if not z.GetIsRuleArea() and z.IsOnLayer(layer)]


def drop_dangling_stitch(board):
    """Delete stitching vias the pour never reached.

    A via is only worth placing where there is copper on at least one end.  The
    filler discards any island it cannot tie to GND -- that is KiCad's default
    island removal, and it is right: a plane that reaches nothing is an antenna,
    not a ground.  A via standing on such an island therefore has nothing to
    stitch and comes out of DRC twice, as `via_dangling` and as an unconnected
    item.

    That is not hypothetical here.  The channel between J1 and J2 -- roughly
    x 12..36, y 15..29, the middle of where the dev board sits -- is fenced off
    from the rest of the plane by the I2S/I2C/BTN traces crossing it, and it
    holds no GND pad to bridge from.  So its pour is one island per layer, both
    are discarded, and every via inside is left hanging.  There is no fix that
    keeps those vias: they would only tie two floating islands to each other.
    Pruning them is the honest answer, and it makes the script self-correcting
    if the routing ever fences off somewhere new.

    Same SWIG caveat as drop_zones(): hand the proxies back.
    """
    # Hoisted out of the loop: the zone lists do not change while we scan, and
    # asking board.Zones() twice per via turned a 210-via sweep into 420 walks of
    # the whole zone container.
    zones = {layer: fill_zones(board, layer)
             for layer in (pcbnew.F_Cu, pcbnew.B_Cu)}
    doomed = []
    for t in list(board.GetTracks()):
        if t.GetClass() != "PCB_VIA" or t.GetNetname() != "GND":
            continue
        pos = t.GetPosition()
        if not any(z.HitTestFilledArea(layer, pos)
                   for layer, zs in zones.items() for z in zs):
            doomed.append(t)
    for v in doomed:
        board.Remove(v)
    return doomed


def add_stitch(board, netcode, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.FromMM(STITCH_D))
    v.SetDrill(pcbnew.FromMM(STITCH_DRILL))
    v.SetNetCode(netcode)
    board.Add(v)


def main():
    board = pcbnew.LoadBoard(BOARD)
    netcode = gnd_netcode(board)

    _keep_alive = drop_zones(board) + drop_stitch_vias(board)   # noqa: F841
    print(f"solid GND connection: {', '.join(solid_gnd(board))}")
    for layer, name in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
        rect_zone(board, layer, netcode,
                  EDGE_INSET, EDGE_INSET, BOARD_W - EDGE_INSET, BOARD_H - EDGE_INSET)
        print(f"zone  GND {name:<4} ({EDGE_INSET},{EDGE_INSET})-"
              f"({BOARD_W - EDGE_INSET},{BOARD_H - EDGE_INSET})  clear={CLEAR}")
    for (hx, hy) in HOLES:
        hole_keepout(board, hx, hy, HOLE_KEEPOUT)
    print(f"rule area: no copper pour within r={HOLE_KEEPOUT} of {len(HOLES)} screw holes")

    nx = int((BOARD_W - 2 * STITCH_EDGE) / STITCH_PITCH)
    ny = int((BOARD_H - 2 * STITCH_EDGE) / STITCH_PITCH)
    placed = skipped = 0
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = STITCH_EDGE + i * STITCH_PITCH
            y = STITCH_EDGE + j * STITCH_PITCH
            if banned(x, y) or not free_for_via(board, x, y):
                skipped += 1
                continue
            add_stitch(board, netcode, x, y)
            placed += 1
    print(f"stitch GND  {placed} via(s) placed, {skipped} lattice point(s) skipped"
          f"  (pitch {STITCH_PITCH} mm)")

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    print(f"filled {len(board.Zones())} zone(s)")

    # Prune-then-refill until it settles.  One pass is normally enough; the loop
    # is here because removing a via changes the copper the filler sees, so in
    # principle a later fill could strand a via that the first pass kept.
    for attempt in range(1, 4):
        _pruned = drop_dangling_stitch(board)     # noqa: F841 -- keep proxies alive
        if not _pruned:
            break
        print(f"pruned {len(_pruned)} stitching via(s) with no pour beneath them"
              f"  (pass {attempt})")
        filler.Fill(board.Zones())
    else:
        print("WARNING: pruning did not settle after 3 passes")

    board.Save(BOARD)
    print("saved", BOARD)


main()

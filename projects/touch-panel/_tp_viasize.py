"""What vias does this board actually use?

VIA_D = 0.60 / VIA_DRILL = 0.30 were inherited from the carrier's route.py, where
they are the right size for a 100x74 power board.  blocked_for() builds its via
mask at CLEAR + VIA_D/2 = 0.46 -- a shell 0.15 mm wider than the trace's own
0.31 -- so on a panel with 2,410 tracks and no zones it covers 57% of the grid.
If the panel's own vias are smaller, that 0.15 mm is being reserved for a via
this board would never place, and the CSELs are failing against a phantom.

GetWidth() on a PCB_VIA asserts without a layer argument (pcb_track.cpp:387);
every call is spelled GetWidth(pcbnew.F_Cu) here so the run stays readable.
"""
import collections
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)

dia = collections.Counter()
drl = collections.Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        dia[round(pcbnew.ToMM(t.GetWidth()), 3)] += 1
        drl[round(pcbnew.ToMM(t.GetDrillValue()), 3)] += 1

print("vias on the board: %d" % sum(dia.values()))
print("\nby diameter (mm):")
for d, n in sorted(dia.items()):
    print("   %.3f   x%-4d  %s" % (d, n, "#" * min(60, n // 4)))
print("\nby drill (mm):")
for d, n in sorted(drl.items()):
    print("   %.3f   x%-4d  %s" % (d, n, "#" * min(60, n // 4)))

ds = board.GetDesignSettings()
print("\nboard design rules:")
for name in ("m_ViasMinSize", "m_MinThroughDrill", "m_TrackMinWidth",
             "m_MinClearance", "m_ViasMinAnnularWidth"):
    try:
        print("   %-22s %.3f mm"
              % (name, pcbnew.ToMM(getattr(ds, name))))
    except Exception as exc:                              # noqa: BLE001
        print("   %-22s unavailable (%s)" % (name, exc))

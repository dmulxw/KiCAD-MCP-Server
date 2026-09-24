"""ASCII occupancy map of the two power clusters.

Throwaway.  Prints what is actually where, so the ref placement is chosen from
the geometry rather than from another round of guess-and-run:

    #  copper (pad or via)      +  silk, ours or a footprint's       .  free

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" .scratch/refmap.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

X0, Y0, X1, Y1 = 62.0, 0.0, 96.0, 17.0
CELL = 0.40

# What each footprint is, so the map can name the parts instead of shading them.
LABEL = {"U1": "U1", "U2": "U2", "C5": "C5", "C6": "C6", "C7": "C7", "C8": "C8",
         "R2": "R2", "R3": "R3", "R4": "R4", "R5": "R5", "L1": "L1", "D2": "D2",
         "D3": "D3", "J5": "J5", "SW5": "S5", "J6": "J6", "J7": "J7"}


def mm(v):
    return pcbnew.ToMM(v)


def main():
    board = pcbnew.LoadBoard(BOARD)
    nx = int((X1 - X0) / CELL)
    ny = int((Y1 - Y0) / CELL)
    grid = [["." for _ in range(nx)] for _ in range(ny)]

    def paint(shape, ch):
        b = shape.BBox()
        i0 = max(0, int((mm(b.GetLeft()) - X0) / CELL))
        i1 = min(nx - 1, int((mm(b.GetRight()) - X0) / CELL))
        j0 = max(0, int((mm(b.GetTop()) - Y0) / CELL))
        j1 = min(ny - 1, int((mm(b.GetBottom()) - Y0) / CELL))
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                if grid[j][i] == ".":
                    grid[j][i] = ch

    for fp in board.GetFootprints():
        for p in fp.Pads():
            paint(p.GetEffectiveShape(pcbnew.F_Cu), "#")
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            paint(t.GetEffectiveShape(pcbnew.F_Cu), "#")
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            paint(d.GetEffectiveShape(pcbnew.F_SilkS), "+")
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS:
                paint(g.GetEffectiveShape(pcbnew.F_SilkS), "+")
        for f in (fp.Reference(), fp.Value()):
            if f.IsVisible() and f.GetLayer() == pcbnew.F_SilkS:
                paint(f.GetEffectiveTextShape(), "+")

    # Name each part at its own body centre, overwriting whatever is under it.
    for fp in board.GetFootprints():
        name = LABEL.get(str(fp.GetReference()))
        if not name:
            continue
        b = fp.GetBoundingBox()
        cx, cy = (mm(b.GetLeft()) + mm(b.GetRight())) / 2.0, (mm(b.GetTop()) + mm(b.GetBottom())) / 2.0
        i, j = int((cx - X0) / CELL), int((cy - Y0) / CELL)
        if 0 <= i < nx and 0 <= j < ny:
            grid[j][i] = name[0]
            if i + 1 < nx:
                grid[j][i + 1] = name[1]

    print("     " + "".join(str(int(X0 + i * CELL) % 10) for i in range(nx)))
    for j in range(ny):
        print(f"{Y0 + j * CELL:5.1f}" + "".join(grid[j]))


main()

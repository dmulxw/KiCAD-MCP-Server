import pcbnew, sys
BOARD = r"YD-ESP32-S3-Carrier.kicad_pcb"
BOARD_W, BOARD_H = 100.0, 64.0
def vec(x, y): return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
def probe(b, tag):
    try:
        print(f"  after {tag:<34} -> {len(list(b.GetFootprints()))}", flush=True); return True
    except Exception as e:
        print(f"  after {tag:<34} RAISED {type(e).__name__}", flush=True); return False

b = pcbnew.LoadBoard(BOARD)
probe(b, "load")

# 1. read the drawings without removing anything
edge = [d for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
print(f"  {len(edge)} Edge.Cuts drawing(s)", flush=True)
probe(b, "read GetDrawings")

# 2. remove them -- keeping the proxies, as the real script does not
for d in edge:
    b.Remove(d)
probe(b, "board.Remove(drawing) x%d" % len(edge))

# 3. add the outline back
for (x0, y0), (x1, y1) in (((0, 0), (BOARD_W, 0)), ((BOARD_W, 0), (BOARD_W, BOARD_H)),
                           ((BOARD_W, BOARD_H), (0, BOARD_H)), ((0, BOARD_H), (0, 0))):
    seg = pcbnew.PCB_SHAPE(b)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetLayer(pcbnew.Edge_Cuts)
    seg.SetWidth(pcbnew.FromMM(0.10))
    seg.SetStart(vec(x0, y0))
    seg.SetEnd(vec(x1, y1))
    b.Add(seg)
probe(b, "add 4 PCB_SHAPE")

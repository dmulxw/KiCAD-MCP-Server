"""Which corridor copper is original design and which is ours?

KiCad writes segments as multi-line records, so a line grep cannot see them and
my earlier per-coordinate greps were reading rounded numbers back out of memory.
This parses both the worktree board and `git show HEAD:` with the same regex,
keeps only segments whose *whole* extent lies in the corridor band, and prints
the two sets side by side so "who put this here" has a definite answer.
"""
import re
import subprocess

WT = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
REPO = r"D:\source\repos\KiCad-MCP-Server"

SEG = re.compile(
    r"\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)"
    r"\s*\(width ([\d.-]+)\)\s*\(layer \"([^\"]+)\"\)\s*\(net \"([^\"]+)\"\)")
VIA = re.compile(
    r"\(via\s*\(at ([\d.-]+) ([\d.-]+)\)\s*\(size ([\d.-]+)\)\s*"
    r"\(drill ([\d.-]+)\)[^)]*\)\s*\(layers \"([^\"]+)\" \"([^\"]+)\"\)"
    r"\s*\(net \"([^\"]+)\"\)")

X0, X1, Y0, Y1 = 98.0, 103.0, 108.0, 248.0


def load(text):
    segs, vias = [], []
    for m in SEG.finditer(text):
        x1, y1, x2, y2, w, layer, net = m.groups()
        x1, y1, x2, y2, w = map(float, (x1, y1, x2, y2, w))
        if X0 <= min(x1, x2) and max(x1, x2) <= X1 and \
           Y0 <= min(y1, y2) and max(y1, y2) <= Y1:
            segs.append((net, layer, x1, y1, x2, y2, w))
    for m in VIA.finditer(text):
        x, y, size, drill, l1, l2, net = m.groups()
        x, y = float(x), float(y)
        if X0 <= x <= X1 and Y0 <= y <= Y1:
            vias.append((net, x, y))
    return segs, vias


wt_text = open(WT, encoding="utf-8", errors="replace").read()
head_text = subprocess.run(
    ["git", "show", "HEAD:projects/touch-panel/touch-panel.kicad_pcb"],
    cwd=REPO, capture_output=True).stdout.decode("utf-8", "replace")

for name, text in (("HEAD", head_text), ("worktree", wt_text)):
    segs, vias = load(text)
    nets = {}
    for s in segs:
        nets.setdefault(s[0], []).append(s)
    print("=" * 70)
    print("%s: %d segment(s) + %d via(s) fully inside x %.1f..%.1f y %.0f..%.0f"
          % (name, len(segs), len(vias), X0, X1, Y0, Y1))
    for net in sorted(nets):
        ss = nets[net]
        xs = sorted(set(round(s[2], 2) for s in ss) | set(round(s[4], 2) for s in ss))
        layers = sorted({s[1] for s in ss})
        w = sorted({round(s[6], 2) for s in ss})
        ys = [s[3] for s in ss] + [s[5] for s in ss]
        print("   %-10s %3d seg  %-11s w=%-12s x %s  y %.2f..%.2f"
              % (net, len(ss), ",".join(l[0] for l in layers),
                 ",".join("%g" % v for v in w),
                 xs[:8], min(ys), max(ys)))
    for v in sorted(vias):
        print("   VIA %-10s (%7.2f,%7.2f)" % v)

# --- what actually differs ------------------------------------------------
h_segs, h_vias = load(head_text)
w_segs, w_vias = load(wt_text)
hs = {(s[0], s[1], round(s[2], 3), round(s[3], 3), round(s[4], 3),
       round(s[5], 3)) for s in h_segs}
ws = {(s[0], s[1], round(s[2], 3), round(s[3], 3), round(s[4], 3),
       round(s[5], 3)) for s in w_segs}
print("\n" + "=" * 70)
print("segment keys in worktree but NOT in HEAD (%d):" % len(ws - hs))
for k in sorted(ws - hs):
    print("   + %-10s %-4s (%8.3f,%8.3f)-(%8.3f,%8.3f)" % (k[0], k[1][0], *k[2:]))
print("segment keys in HEAD but NOT in worktree (%d):" % len(hs - ws))
for k in sorted(hs - ws):
    print("   - %-10s %-4s (%8.3f,%8.3f)-(%8.3f,%8.3f)" % (k[0], k[1][0], *k[2:]))

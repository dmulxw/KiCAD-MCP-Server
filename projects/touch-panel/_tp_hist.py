"""Which of the corridor's blocking segments did we add, and which were here?"""
import io
import re
import subprocess

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"

seg = re.compile(
    r"\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)"
    r"\s*\(width ([\d.-]+)\)\s*\(layer \"([^\"]+)\"\)\s*\(net \"([^\"]+)\"\)")


def load(text):
    out = {}
    for m in seg.finditer(text):
        x1, y1, x2, y2, w, layer, net = m.groups()
        key = (round(float(x1), 4), round(float(y1), 4),
               round(float(x2), 4), round(float(y2), 4), layer, net)
        out[key] = float(w)
    return out


work = load(io.open(HERE + r"\touch-panel.kicad_pcb", encoding="utf-8").read())
head = load(subprocess.run(
    ["git", "show", "HEAD:projects/touch-panel/touch-panel.kicad_pcb"],
    cwd=r"D:\source\repos\KiCad-MCP-Server", capture_output=True, text=True,
    encoding="utf-8").stdout)

print("worktree %d segments   HEAD %d segments" % (len(work), len(head)))
added = set(work) - set(head)
gone = set(head) - set(work)
print("added %d   removed %d" % (len(added), len(gone)))

X0, X1, Y0, Y1 = 99.0, 104.0, 200.0, 222.0
print("\nsegments in the corridor x %.1f..%.1f y %.1f..%.1f:" % (X0, X1, Y0, Y1))
for tag, s in (("HEAD", head), ("WORK", work)):
    print("  -- %s --" % tag)
    for k in sorted(s):
        x1, y1, x2, y2, layer, net = k
        if X0 <= min(x1, x2) and max(x1, x2) <= X1 and Y0 <= min(y1, y2) and max(y1, y2) <= Y1:
            print("     %-8s %-6s w=%.2f (%.2f,%.2f)-(%.2f,%.2f)"
                  % (net, layer, s[k], x1, y1, x2, y2))

print("\nby net, added segments:")
from collections import Counter
print("  ", Counter(k[5] for k in added).most_common(12))
print("by net, removed segments:")
print("  ", Counter(k[5] for k in gone).most_common(12))

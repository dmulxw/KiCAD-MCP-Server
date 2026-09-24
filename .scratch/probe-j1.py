"""Everything on the board within `radius` of a point, with distances.

Static parse of the .kicad_pcb -- no pcbnew, so it runs on the host. Reports
tracks, vias and pads near a coordinate along with the net they belong to, so
the copper sealing an escape can be named.

    python .scratch/probe-j1.py <board> <x> <y> [radius]
"""

import math
import sys


# --------------------------------------------------------------------------
# a small s-expression reader
# --------------------------------------------------------------------------


def tokenize(text):
    """Yield '(', ')' and atoms, skipping quoted-string internals."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            yield ("str", "".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield ("atom", text[i:j])
            i = j


def parse(text):
    """Parse the whole document into nested lists."""
    stack = [[]]
    for tok in tokenize(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    return stack[0]


def head(node):
    if isinstance(node, list) and node and isinstance(node[0], tuple):
        return node[0][1]
    return None


def atom(node):
    return node[1] if isinstance(node, tuple) else None


def num(node):
    try:
        return float(atom(node))
    except (TypeError, ValueError):
        return None


def kids(node, name):
    return [c for c in node if isinstance(c, list) and head(c) == name]


def kid(node, name):
    k = kids(node, name)
    return k[0] if k else None


def coords(node):
    """(x, y) taken from the node's own first two operands."""
    if not node or len(node) < 3:
        return None
    x, y = num(node[1]), num(node[2])
    return None if x is None or y is None else (x, y)


def origin(node):
    """(x, y) of an `(at x y [rot])` child, or None."""
    return coords(kid(node, "at")) if node else None


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


def point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def main():
    board, px, py = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    radius = float(sys.argv[4]) if len(sys.argv) > 4 else 1.2
    doc = parse(open(board, encoding="utf-8", errors="replace").read())
    root = doc[0]

    hits = []

    def netname(node):
        n = kid(node, "net")
        if not n:
            return "-"
        for c in n[1:]:
            if isinstance(c, tuple) and c[0] == "str":
                return c[1]
        return atom(n[1]) if len(n) > 1 else "-"

    for seg in kids(root, "segment"):
        a, b = coords(kid(seg, "start")), coords(kid(seg, "end"))
        w = num(kid(seg, "width")[1]) if kid(seg, "width") else None
        lay = kid(seg, "layer")
        if not (a and b and w):
            continue
        d = point_seg_dist(px, py, a[0], a[1], b[0], b[1])
        if d - w / 2 <= radius:
            hits.append((d, "track", w, atom(lay[1]) if lay else "?",
                         netname(seg), f"({a[0]},{a[1]})->({b[0]},{b[1]})"))

    for via in kids(root, "via"):
        at = origin(via)
        sz = kid(via, "size")
        if not (at and sz):
            continue
        w = num(sz[1])
        d = math.hypot(px - at[0], py - at[1])
        if d - w / 2 <= radius:
            hits.append((d, "via", w, "all", netname(via),
                         f"({at[0]},{at[1]}) drill "
                         f"{num(kid(via, 'drill')[1]) if kid(via, 'drill') else '?'}"))

    for fp in kids(root, "footprint"):
        ref = "?"
        for prop in kids(fp, "property"):
            if len(prop) > 2 and atom(prop[1]) == "Reference":
                ref = atom(prop[2])
        for pad in kids(fp, "pad"):
            at = origin(pad)
            sz = kid(pad, "size")
            if not (at and sz):
                continue
            w, h = num(sz[1]), num(sz[2])
            layers = [atom(l[1]) for l in kids(pad, "layers") if len(l) > 1]
            d = math.hypot(px - at[0], py - at[1])
            if d <= radius + max(w, h):
                hits.append((d, "pad", min(w, h), "/".join(layers) or "?",
                             netname(pad),
                             f"{ref}.{atom(pad[1])} at ({at[0]:.4f},{at[1]:.4f}) "
                             f"size {w}x{h}"))

    hits.sort()
    print(f"items within {radius}mm of ({px}, {py}):  {len(hits)}")
    print(f"{'dist':>7} {'kind':5} {'size':>5} {'layer':8} {'net':>8}  detail")
    for d, kind, w, ly, nt, detail in hits:
        print(f"{d:7.3f} {kind:5} {w:5} {ly:8} {nt:>8}  {detail}")


if __name__ == "__main__":
    main()

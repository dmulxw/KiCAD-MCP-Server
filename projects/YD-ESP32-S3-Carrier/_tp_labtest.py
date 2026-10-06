"""Settle the labeller against ground truth on grids small enough to trust.

_tp_comp.py's run-and-union labeller says chip A's component is 331k cells where
the wavefront reaches 127k, and the wavefront's set is strictly inside the
labeller's.  One of the two is wrong and reasoning has not found it, so stop
reasoning: build a grid small enough to compute connected components by a method
that cannot be wrong (min-label propagation to a fixpoint), and compare.

The move model under test is the one both programs claim to implement:
  * 8-connected within a layer, a diagonal only when BOTH orthogonal neighbours
    are legal;
  * the two layers joined wherever a via is legal.
"""
import sys

import numpy as np

sys.path.insert(0, ".")

from _tp_label import label_free          # noqa: E402


def truth(OK, VOK, layers, nx, ny):
    """Components by min-label propagation.  Cannot be clever, cannot be wrong.

    Each node starts as its own label; repeatedly every node takes the smallest
    label among its legal neighbours.  Legal edges only, so a labelling that
    respects the move model exactly is the fixpoint, and the number of distinct
    labels is the component count.

    Absent neighbours must be BIG, not -1: the reduction is a minimum, so a -1
    sentinel would win every time and a cell with one blocked neighbour would
    never accept a label at all -- which reads as "every cell is its own
    component" and looks exactly like a labeller bug.
    """
    BIG = np.int64(1) << 62
    lab = {}
    base = 0
    for lay in layers:
        idx = np.arange(base, base + ny * nx, dtype=np.int64).reshape(ny, nx)
        lab[lay] = np.where(OK[lay], idx, BIG)
        base += ny * nx

    ok = {lay: OK[lay] for lay in layers}
    for _ in range(200000):
        changed = False
        new = {}
        for lay in layers:
            l = lab[lay]
            props = []
            up = np.full_like(l, BIG); up[1:, :] = l[:-1, :]; props.append(up)
            dn = np.full_like(l, BIG); dn[:-1, :] = l[1:, :]; props.append(dn)
            lf = np.full_like(l, BIG); lf[:, 1:] = l[:, :-1]; props.append(lf)
            rt = np.full_like(l, BIG); rt[:, :-1] = l[:, 1:]; props.append(rt)
            # diagonals, each gated by its two orthogonal corner cells
            ul = np.full_like(l, BIG)
            ul[1:, 1:] = np.where(ok[lay][1:, 1:] & ok[lay][:-1, 1:]
                                  & ok[lay][1:, :-1], l[:-1, :-1], BIG)
            props.append(ul)
            ur = np.full_like(l, BIG)
            ur[1:, :-1] = np.where(ok[lay][1:, :-1] & ok[lay][:-1, :-1]
                                   & ok[lay][1:, 1:], l[:-1, 1:], BIG)
            props.append(ur)
            dl = np.full_like(l, BIG)
            dl[:-1, 1:] = np.where(ok[lay][:-1, 1:] & ok[lay][1:, 1:]
                                   & ok[lay][:-1, :-1], l[1:, :-1], BIG)
            props.append(dl)
            dr = np.full_like(l, BIG)
            dr[:-1, :-1] = np.where(ok[lay][:-1, :-1] & ok[lay][1:, :-1]
                                    & ok[lay][:-1, 1:], l[1:, 1:], BIG)
            props.append(dr)
            m = np.minimum.reduce(props)
            out = np.where(ok[lay] & (m < BIG), np.minimum(l, m), l)
            if not np.array_equal(out, l):
                changed = True
            new[lay] = out
        a0, a1 = layers
        both = VOK & ok[a0] & ok[a1]
        if both.any():
            m = np.minimum(new[a0], new[a1])
            for lay in layers:
                o = np.where(both & (m < BIG), np.minimum(new[lay], m), new[lay])
                if not np.array_equal(o, new[lay]):
                    changed = True
                new[lay] = o
        lab = new
        if not changed:
            break

    # compress: lab holds ORIGINAL node ids, so map node id -> 0..K-1
    allv = np.concatenate([lab[l][lab[l] < BIG] for l in layers])
    uniq, inv = np.unique(allv, return_inverse=True)
    remap = np.full(base, -1, np.int64)
    remap[allv] = inv
    out = {}
    for lay in layers:
        m = lab[lay] < BIG
        c = np.full(lab[lay].shape, -1, np.int32)
        c[m] = remap[lab[lay][m]]
        out[lay] = c
    return out, len(uniq)


def check(tag, OK, VOK, layers=(0, 2)):
    ny, nx = OK[layers[0]].shape
    t, Kt = truth(OK, VOK, layers, nx, ny)
    L, Kl = label_free(OK, VOK, layers, nx, ny)

    def part(comp):
        """Partition as a canonical set of frozensets of (layer, j, i)."""
        groups = {}
        for lay in layers:
            c = comp[lay]
            j, i = np.nonzero(c >= 0)
            for a, b, k in zip(j.tolist(), i.tolist(), c[j, i].tolist()):
                groups.setdefault(int(k), set()).add((lay, a, b))
        return frozenset(frozenset(v) for v in groups.values())

    pt, pl = part(t), part(L)
    same = pt == pl
    print("  %-34s truth %3d comps   labeller %3d comps   %s"
          % (tag, Kt, Kl, "AGREE" if same else "DISAGREE"))
    if not same:
        big_t = max(pt, key=len)
        big_l = max(pl, key=len)
        print("        largest truth %d cells, largest labeller %d cells"
              % (len(big_t), len(big_l)))
        # the offending run: a labeller group that spans two truth groups
        for g in pl:
            hit = [h for h in pt if g & h]
            if len(hit) > 1:
                ex = sorted(g)[0]
                print("        labeller group of %d spans %d truth groups"
                      % (len(g), len(hit)))
                for h in hit[:4]:
                    xs = sorted(h)
                    print("           truth group %4d cells, e.g. (%d, %d, %d)"
                          % (len(h), xs[0][0], xs[0][1], xs[0][2]))
                break
    return same


rng = np.random.default_rng(7)
ny, nx = 24, 32
layers = (0, 2)

# 1. open field with scattered obstacles
OK = {l: rng.random((ny, nx)) > 0.35 for l in layers}
VOK = (rng.random((ny, nx)) > 0.7) & OK[0] & OK[2]
check("scattered obstacles", OK, VOK)

# 2. same obstacles on both layers -- the real board's thin-corridor case
OK = {l: (rng.random((ny, nx)) > 0.55) for l in layers}
OK[2] = OK[0].copy()
VOK = (rng.random((ny, nx)) > 0.6) & OK[0]
check("identical layers", OK, VOK)

# 3. horizontal stripes: dense, mostly-1-cell corridors
stripe = np.zeros((ny, nx), bool)
stripe[::2, :] = True
OK = {l: stripe.copy() for l in layers}
VOK = np.zeros((ny, nx), bool)
check("1-cell corridors", OK, VOK)

# 4. same, with vias allowed on every corridor cell
VOK = stripe.copy()
check("1-cell corridors + vias", OK, VOK)

# 5. vertical stripes on one layer, horizontal on the other -- only vias join
OKv = np.zeros((ny, nx), bool); OKv[:, ::2] = True
OKh = np.zeros((ny, nx), bool); OKh[::2, :] = True
check("crossed stripes, via-only", {0: OKv, 2: OKh}, OKv & OKh)

# 6. a single diagonal squeeze: two blocks meeting corner to corner
A = np.zeros((ny, nx), bool)
A[:12, :16] = True
A[12:, 16:] = True
OK = {l: A.copy() for l in layers}
check("corner-to-corner contact", OK, np.zeros((ny, nx), bool))

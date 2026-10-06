"""The run-and-union labeller, on its own so it can be tested in isolation.

_tp_comp.py calls it and _tp_labtest.py tests it; both import THIS file, so a fix
here is a fix in the thing that was measured -- not in a copy of it.
"""
import numpy as np


def label_free(OK, VOK, layers, nx, ny, quiet=False):
    """8-connected components within a layer, joined across layers by vias.

    Run-length + union-find.  A per-cell flood would need one pass per seed set;
    this needs one pass for the whole board, and then every site and every net is
    a lookup.
    """
    rows, rid = {}, {}
    total = 0
    for lay in layers:
        r = np.full((ny, nx), -1, np.int32)
        rl = []
        for j in range(ny):
            row = OK[lay][j]
            if not row.any():
                rl.append((total, np.empty(0, np.int64), np.empty(0, np.int64)))
                continue
            d = np.diff(row.astype(np.int8))
            s = np.flatnonzero(d == 1) + 1
            e = np.flatnonzero(d == -1) + 1
            if row[0]:
                s = np.r_[np.int64(0), s]
            if row[-1]:
                e = np.r_[e, np.int64(nx)]
            rl.append((total, s, e))
            for k in range(len(s)):
                r[j, s[k]:e[k]] = total + k
            total += len(s)
        rid[lay] = r
        rows[lay] = rl
        if not quiet:
            print("  layer %d: %d runs" % (lay, total))

    parent = np.arange(total, dtype=np.int64)

    def find(a):
        root = int(a)
        while parent[root] != root:
            root = int(parent[root])
        a = int(a)
        while parent[a] != root:
            parent[a], a = root, int(parent[a])
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Two cells in adjacent rows are joined exactly when they share a column --
    # i.e. when the two runs OVERLAP.  Nothing wider: a run is maximal, so two
    # adjacent legal cells in one row are always in the same run, and that makes
    # the diagonal redundant.  A diagonal (j-1,x) <-> (j,x+-1) needs its two
    # corner cells legal, which puts x and x+-1 in one run of row j-1 AND one run
    # of row j -- so the runs already share column x.  Dilating the runs instead
    # ("do they come within one cell?") joins runs whose corner cells are exactly
    # the blockers, which is the mistake that made the first version of this file
    # merge 547k cells where the wavefront finds 122k.
    #
    # Overlap as a range test: (pe > cs) and (ps < ce).  The runs with pe > cs
    # are a SUFFIX of the start-sorted list and those with ps < ce are a PREFIX,
    # so their intersection is contiguous on both sides.
    nrow = 0
    for lay in layers:
        for j in range(1, ny):
            b0, ps, pe = rows[lay][j - 1]
            b1, cs, ce = rows[lay][j]
            if len(ps) == 0 or len(cs) == 0:
                continue
            lo = np.searchsorted(pe, cs, "right")            # idx of first pe > cs
            hi = np.searchsorted(ps, ce - 1, "right") - 1    # idx of last ps < ce
            bad = lo > hi
            if bad.all():
                continue
            kmax = int((hi - lo).max())
            for k in range(kmax + 1):
                sel = (lo + k) <= hi
                if not sel.any():
                    break
                t = np.flatnonzero(sel)
                for a, b in zip((b1 + t).tolist(), (b0 + lo[t] + k).tolist()):
                    union(a, b)
                    nrow += 1

    # Vias join the layers.  Only the distinct run pairs matter, so collapse.
    nvia = 0
    a0, a1 = layers
    sel = VOK & (rid[a0] >= 0) & (rid[a1] >= 0)
    if sel.any():
        pr = np.unique(np.stack([rid[a0][sel], rid[a1][sel]], 1), axis=0)
        for a, b in zip(pr[:, 0].tolist(), pr[:, 1].tolist()):
            union(a, b)
            nvia += 1
    if not quiet:
        print("  %d row unions, %d via unions" % (nrow, nvia))

    roots = np.array([find(i) for i in range(total)], dtype=np.int64)
    uniq, inv = np.unique(roots, return_inverse=True)
    comp = {}
    for lay in layers:
        r = rid[lay]
        c = np.full(r.shape, -1, np.int32)
        m = r >= 0
        c[m] = inv[r[m]]
        comp[lay] = c
    return comp, len(uniq)

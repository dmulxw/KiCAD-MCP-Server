"""Reconnaissance for the split-connector / widen-board / window-cutout redesign.

The instruction assumes four things that have to be checked before a single
line is drawn:

1. That the touch electrodes leave room somewhere. 210 pads of 5.00 x 5.00mm
   on B.Cu cover half this board; if they run edge to edge there is no strip
   for a widened border to free up, and no middle region to cut a window into.
2. Where the "4 conductive-adhesive regions" are. They are not named in the
   board file, so they have to be inferred from the footprint set -- mounting
   holes, fiducials, the connector, anything mechanical.
3. What the outline is today and what is already on Edge.Cuts.
4. What widening by 5-10mm per side would actually buy, measured as free area
   on both copper layers rather than assumed.

    python recon.py <board>
"""

import argparse
from collections import defaultdict

import pcbnew

S = 1e6


def mm(v):
    return v / S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    bb = board.GetBoardEdgesBoundingBox()
    print(f"outline bbox  x {mm(bb.GetLeft()):8.3f} .. {mm(bb.GetRight()):8.3f}"
          f"   ({mm(bb.GetWidth()):.3f} wide)")
    print(f"              y {mm(bb.GetTop()):8.3f} .. {mm(bb.GetBottom()):8.3f}"
          f"   ({mm(bb.GetHeight()):.3f} tall)")
    print(f"copper layers: {board.GetCopperLayerCount()}")

    print("\nEdge.Cuts items:")
    n = 0
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        n += 1
        cls = d.GetClass()
        try:
            s, e = d.GetStart(), d.GetEnd()
            print(f"  {cls:<12} ({mm(s.x):8.3f},{mm(s.y):8.3f}) -> "
                  f"({mm(e.x):8.3f},{mm(e.y):8.3f})")
        except AttributeError:
            print(f"  {cls:<12} (no start/end)")
    print(f"  total {n}")

    # --- the electrode array ------------------------------------------------
    pads = [(fp, p) for fp in board.GetFootprints() for p in fp.Pads()]
    elec = [(fp, p) for fp, p in pads if p.GetNetname().startswith("PAD")]
    print(f"\nelectrode pads (net PAD*): {len(elec)}")
    if elec:
        xs = sorted({round(mm(p.GetPosition().x), 2) for _, p in elec})
        ys = sorted({round(mm(p.GetPosition().y), 2) for _, p in elec})
        ex0 = min(mm(p.GetBoundingBox().GetLeft()) for _, p in elec)
        ex1 = max(mm(p.GetBoundingBox().GetRight()) for _, p in elec)
        ey0 = min(mm(p.GetBoundingBox().GetTop()) for _, p in elec)
        ey1 = max(mm(p.GetBoundingBox().GetBottom()) for _, p in elec)
        print(f"  copper extent x {ex0:8.3f} .. {ex1:8.3f}   "
              f"y {ey0:8.3f} .. {ey1:8.3f}")
        print(f"  strip left of electrodes : {ex0 - mm(bb.GetLeft()):7.3f}mm")
        print(f"  strip right of electrodes: {mm(bb.GetRight()) - ex1:7.3f}mm")
        print(f"  strip above electrodes   : {ey0 - mm(bb.GetTop()):7.3f}mm")
        print(f"  strip below electrodes   : {mm(bb.GetBottom()) - ey1:7.3f}mm")
        print(f"  distinct x centres: {len(xs)}  -> {xs[:6]}"
              f"{' ...' if len(xs) > 6 else ''}")
        print(f"  distinct y centres: {len(ys)}  -> {ys[:6]}"
              f"{' ...' if len(ys) > 6 else ''}")
        if len(xs) > 1:
            print(f"  x pitch: {xs[1]-xs[0]:.3f}mm, max gap "
                  f"{max(b - a for a, b in zip(xs, xs[1:])):.3f}mm")
        if len(ys) > 1:
            print(f"  y pitch: {ys[1]-ys[0]:.3f}mm, max gap "
                  f"{max(b - a for a, b in zip(ys, ys[1:])):.3f}mm")

    # --- everything else, by reference prefix --------------------------------
    print("\nfootprints by prefix:")
    groups = defaultdict(list)
    for fp in board.GetFootprints():
        r = fp.GetReference()
        groups["".join(c for c in r if not c.isdigit()) or "?"].append(fp)
    for pre, fps in sorted(groups.items(), key=lambda t: -len(t[1])):
        if pre == "PAD":
            continue
        print(f"  {pre:<6} {len(fps):4d}")

    print("\nmechanical / named footprints:")
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if not (r.startswith("MH") or r.startswith("MK") or r.startswith("J")):
            continue
        pos = fp.GetPosition()
        fbb = fp.GetBoundingBox()
        print(f"  {r:<5} {str(fp.GetFPID().GetLibItemName()):<45} "
              f"({mm(pos.x):8.3f},{mm(pos.y):8.3f})  "
              f"size {mm(fbb.GetWidth()):6.2f} x {mm(fbb.GetHeight()):6.2f}  "
              f"layer {fp.GetLayerName()}")

    # --- what a wider board would gain --------------------------------------
    # Only B.Cu matters for the electrodes, but a header is through-hole, so
    # the question is how far the free strip extends on BOTH layers.
    print("\nfree strip beside the electrodes (both copper layers clear):")
    bpads = [p for _, p in pads]
    for side, x0, x1 in (("left", mm(bb.GetLeft()) - 10, mm(bb.GetLeft()) + 6),
                         ("right", mm(bb.GetRight()) - 6, mm(bb.GetRight()) + 10)):
        cols = {}
        for fp, p in pads:
            pbb = p.GetBoundingBox()
            if mm(pbb.GetRight()) < x0 or mm(pbb.GetLeft()) > x1:
                continue
            if not p.IsOnLayer(pcbnew.B_Cu):
                continue
            c0 = round(mm(pbb.GetLeft()), 1)
            c1 = round(mm(pbb.GetRight()), 1)
            cols[(c0, c1)] = cols.get((c0, c1), 0) + 1
        print(f"  {side} x[{x0:.2f},{x1:.2f}]: "
              f"{len(cols)} distinct B.Cu pad column(s)")
        for (c0, c1), cnt in sorted(cols.items())[:8]:
            print(f"      x {c0:8.2f}..{c1:8.2f}  ({cnt} pads)")


if __name__ == "__main__":
    main()

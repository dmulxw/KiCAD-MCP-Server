"""Crop a mm-rectangle out of a board render, using the outline to calibrate.

kicad-cli fits the board to the image with margins, so the px/mm scale is not
obvious. Edge.Cuts gives us a rectangle we can locate in the raster and solve
for the affine map.
"""
import sys

from PIL import Image

SRC, OUT = sys.argv[1], sys.argv[2]
X0, Y0, X1, Y1 = (float(v) for v in sys.argv[3:7])
BW, BH = (float(v) for v in sys.argv[7:9])      # board mm size
MARGIN, SCALE = 0.0, int(sys.argv[9]) if len(sys.argv) > 9 else 3

im = Image.open(SRC).convert("RGB")
W, H = im.size
px = im.load()

# The drawing sheet / background is near-white; copper and outline are not.
# Find the tight ink bbox -- with only Edge.Cuts + copper shown, that is the
# board outline (copper never leaves it).
xs, ys = [], []
for yy in range(0, H):
    for xx in range(0, W):
        r, g, bl = px[xx, yy]
        if r < 200 or g < 200 or bl < 200:
            xs.append(xx)
            ys.append(yy)
            break
    else:
        continue
    for xx in range(W - 1, -1, -1):
        r, g, bl = px[xx, yy]
        if r < 200 or g < 200 or bl < 200:
            xs.append(xx)
            break
for xx in range(0, W):
    for yy in range(0, H):
        r, g, bl = px[xx, yy]
        if r < 200 or g < 200 or bl < 200:
            ys.append(yy)
            break
    else:
        continue
    for yy in range(H - 1, -1, -1):
        r, g, bl = px[xx, yy]
        if r < 200 or g < 200 or bl < 200:
            ys.append(yy)
            break

bx0, bx1 = min(xs), max(xs)
by0, by1 = min(ys), max(ys)
print(f"image {W}x{H}  ink bbox px x[{bx0},{bx1}] y[{by0},{by1}] "
      f"= {bx1-bx0}x{by1-by0} px")
print(f"board {BW}x{BH} mm -> {((bx1-bx0)/BW):.4f} px/mm x, "
      f"{((by1-by0)/BH):.4f} px/mm y")

# Board origin (min corner) in mm is (99.950, 99.950) on this board; the ink
# bbox min corner is the board's min corner.
ORIGIN_X, ORIGIN_Y = 99.950, 99.950
sx = (bx1 - bx0) / BW
sy = (by1 - by0) / BH


def px_of(x, y):
    return bx0 + (x - ORIGIN_X) * sx, by0 + (y - ORIGIN_Y) * sy


c0 = px_of(X0 - MARGIN, Y0 - MARGIN)
c1 = px_of(X1 + MARGIN, Y1 + MARGIN)
box = (int(c0[0]), int(c0[1]), int(c1[0]) + 1, int(c1[1]) + 1)
print(f"crop mm ({X0},{Y0})-({X1},{Y1}) -> px {box}")
im.crop(box).resize(((box[2] - box[0]) * SCALE, (box[3] - box[1]) * SCALE),
                    Image.NEAREST).save(OUT)
print(f"wrote {OUT}")

"""Rasterise the plotted PDFs and crop to the drawn content."""
import pymupdf
from PIL import Image

for name in ("front", "back"):
    root = (r"D:\source\repos\KiCAD-MCP-Server\projects"
            rf"\YD-ESP32-S3-Carrier\preview\{name}")
    doc = pymupdf.open(root + ".pdf")
    page = doc[0]
    print(f"{name}: page {page.rect.width:.0f}x{page.rect.height:.0f} pt")
    page.get_pixmap(dpi=300).save(root + "_full.png")
    im = Image.open(root + "_full.png").convert("RGB")
    bbox = Image.eval(im, lambda p: p < 250).getbbox()
    pad = 40
    box = (max(bbox[0]-pad, 0), max(bbox[1]-pad, 0),
           min(bbox[2]+pad, im.width), min(bbox[3]+pad, im.height))
    im.crop(box).save(root + "_plot.png")
    print(f"   -> {name}.png  {box[2]-box[0]}x{box[3]-box[1]} (from {im.width}x{im.height})")
    doc.close()

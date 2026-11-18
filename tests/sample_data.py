"""Generator for synthetic shipping-label PDFs used by the tests.

Labels contain real VECTOR Code128 barcodes and QR codes (reportlab), optionally a
raster QR image, and unique ORDER-nnnn markers so tests can track every label.
Requires reportlab and Pillow (see requirements-dev.txt).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

LABEL = (288.0, 432.0)
A4 = (595.276, 841.89)
FIVE_BY_SEVEN = (360.0, 504.0)


@dataclass
class LabelSpec:
    platform: Optional[str]          # "ebay", "tiktok", "inpost", "both", "ebay_inpost" or None (no platform text)
    order: str                       # unique marker, e.g. "ORDER-0001"
    x: float = 0.0                   # top-left offset on the page (points)
    y: float = 0.0
    w: float = LABEL[0]
    h: float = LABEL[1]
    raster_qr: bool = False          # add a raster QR-like image
    platform_as_image: bool = False  # draw the platform name as a picture (OCR test)


def _name_image(text: str) -> ImageReader:
    img = Image.new("RGB", (520, 140), "white")
    ImageDraw.Draw(img).text((10, 10), text, fill="black", font=ImageFont.load_default(size=100))
    return ImageReader(img)


def _raster_qr() -> ImageReader:
    img = Image.new("RGB", (60, 60), "white")
    px = img.load()
    for i in range(60):
        for j in range(60):
            if (i * 7 + j * 13 + (i * j) % 5) % 3 == 0:
                px[i, j] = (0, 0, 0)
    return ImageReader(img)


def draw_label(c: canvas.Canvas, page_h: float, spec: LabelSpec) -> None:
    x0, w, h = spec.x, spec.w, spec.h
    y0 = page_h - spec.y - h                      # bottom edge in PDF coordinates
    c.setLineWidth(1.5)
    c.rect(x0 + 4, y0 + 4, w - 8, h - 8)
    names = {"ebay": ["eBay"], "tiktok": ["TikTok Shop"], "both": ["eBay", "TikTok Shop"],
             "inpost": ["InPost shop"], "ebay_inpost": ["eBay", "InPost shop"], None: []}[spec.platform]
    top = y0 + h - 34
    if spec.platform_as_image and names:
        c.drawImage(_name_image(names[0]), x0 + 14, top - 40, width=130, height=35)
        top -= 44
    else:
        c.setFont("Helvetica-Bold", 20)
        for name in names:
            c.drawString(x0 + 14, top, name)
            top -= 24
    c.setFont("Helvetica", 10)
    c.drawString(x0 + 14, top, "Standard shipping - 1 of 1")
    for n, line in enumerate(["SHIP TO:", "JANE DOE", "123 MAIN STREET APT 4", "SPRINGFIELD IL 62704-1234"]):
        c.drawString(x0 + 14, top - 28 - n * 14, line)
    c.drawString(x0 + 14, top - 100, f"Order # {spec.order}")
    tracking = "9400" + "".join(ch for ch in spec.order if ch.isdigit()).zfill(8) + "1899223344"
    c.drawString(x0 + 14, top - 114, f"Tracking {tracking}")
    code128.Code128(tracking, barHeight=60, barWidth=1.0).drawOn(c, x0 + 16, y0 + 120)
    qr = QrCodeWidget(spec.order + tracking, barWidth=80, barHeight=80)
    drawing = Drawing(80, 80)
    drawing.add(qr)
    renderPDF.draw(drawing, c, x0 + w - 110, y0 + 24)
    if spec.raster_qr:
        c.drawImage(_raster_qr(), x0 + 16, y0 + 24, width=60, height=60)


def build_pdf(path: Path, pages: Sequence[tuple[tuple[float, float], Sequence[LabelSpec]]]) -> Path:
    """pages = [((width, height), [LabelSpec, ...]), ...]"""
    c = canvas.Canvas(str(path), pagesize=pages[0][0], pageCompression=0)
    for size, labels in pages:
        c.setPageSize(size)
        for spec in labels:
            draw_label(c, size[1], spec)
        c.showPage()
    c.save()
    return Path(path)


def label_page(platform: Optional[str], order: str, **kw):
    return (LABEL, [LabelSpec(platform, order, **kw)])


def a4_two_up(first: LabelSpec, second: LabelSpec):
    """Two labels side by side near the top of an A4 page."""
    first.x, first.y = 2.0, 40.0
    second.x, second.y = 2.0 + 288 + 15, 40.0
    return (A4, [first, second])

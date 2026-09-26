"""Extract text, tables, speaker notes and image inventory from a .pptx or .pdf deck.

Deck content is treated strictly as data: nothing found in a slide is ever
executed or interpreted as an instruction to this program.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

EMU_PER_INCH = 914400


@dataclass
class TextBlock:
    text: str
    kind: str = "text"          # text / table_row / notes / title
    shape: str = ""


@dataclass
class SlideInfo:
    index: int                  # 1-based slide or page number
    blocks: list[TextBlock] = field(default_factory=list)
    images: list[str] = field(default_factory=list)       # descriptions of picture shapes
    large_image_area: float = 0.0                          # share of slide covered by pictures

    @property
    def text_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks if b.kind != "notes")


@dataclass
class DeckDump:
    path: str
    kind: str                   # pptx / pdf
    slides: list[SlideInfo]

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def unit(self) -> str:
        return "Slide" if self.kind == "pptx" else "Page"


def extract_deck(path: str) -> DeckDump:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pptx":
        return _extract_pptx(path)
    if ext == ".pdf":
        return _extract_pdf(path)
    raise ValueError(f"Unsupported deck format: {ext} (expected .pptx or .pdf)")


def _clean(s: str) -> str:
    return " ".join(s.replace("\x0b", " ").split())


def _extract_pptx(path: str) -> DeckDump:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(path)
    slide_area = float(prs.slide_width * prs.slide_height)
    slides = []
    for i, s in enumerate(prs.slides, 1):
        info = SlideInfo(i)
        pic_area = 0.0

        def walk(shapes):
            nonlocal pic_area
            for sh in shapes:
                if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                    walk(sh.shapes)
                    continue
                if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                    # Keep paragraph breaks as " | " so labels stay attached to values
                    paras = [_clean(p.text) for p in sh.text_frame.paragraphs]
                    t = " | ".join(p for p in paras if p)
                    if t:
                        info.blocks.append(TextBlock(t, "text", sh.name))
                if getattr(sh, "has_table", False) and sh.has_table:
                    for row in sh.table.rows:
                        cells = [_clean(c.text) for c in row.cells]
                        info.blocks.append(TextBlock(" || ".join(cells), "table_row", sh.name))
                if getattr(sh, "has_chart", False) and sh.has_chart:
                    for plot in sh.chart.plots:
                        cats = list(plot.categories)
                        for ser in plot.series:
                            info.blocks.append(TextBlock(
                                f"Chart series {ser.name}: " + ", ".join(
                                    f"{c}={v}" for c, v in zip(cats, ser.values)), "chart", sh.name))
                if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    w, h = sh.width or 0, sh.height or 0
                    pic_area = max(pic_area, (w * h) / slide_area if slide_area else 0)
                    info.images.append(f"{sh.name} ({w / EMU_PER_INCH:.1f}x{h / EMU_PER_INCH:.1f} in)")

        walk(s.shapes)
        info.large_image_area = pic_area
        if s.has_notes_slide:
            notes = _clean(s.notes_slide.notes_text_frame.text)
            if notes:
                info.blocks.append(TextBlock(notes, "notes", "Speaker notes"))
        slides.append(info)
    return DeckDump(path, "pptx", slides)


def _extract_pdf(path: str) -> DeckDump:
    import pymupdf

    doc = pymupdf.open(path)
    slides = []
    for i, page in enumerate(doc, 1):
        info = SlideInfo(i)
        for line in page.get_text("text").splitlines():
            if line.strip():
                info.blocks.append(TextBlock(_clean(line), "text", "page text"))
        try:
            for tab in page.find_tables().tables:
                for row in tab.extract():
                    info.blocks.append(TextBlock(" || ".join(_clean(c or "") for c in row),
                                                 "table_row", "table"))
        except Exception:  # table detection is best-effort
            pass
        area = float(page.rect.width * page.rect.height) or 1.0
        pic = 0.0
        for img in page.get_image_info():
            x0, y0, x1, y1 = img["bbox"]
            pic = max(pic, (x1 - x0) * (y1 - y0) / area)
            info.images.append(f"image {x1 - x0:.0f}x{y1 - y0:.0f} pt")
        info.large_image_area = pic
        slides.append(info)
    return DeckDump(path, "pdf", slides)


def slide_images(path: str, indices: list[int], max_px: int = 1568, min_area: float = 0.15,
                 max_images: int = 12) -> list[tuple[int, str, bytes]]:
    """PNG renderings of large pictures on the given slides (pptx) or of whole pages (pdf).

    Used only to let a vision model read figures that text extraction cannot see.
    Returns (slide_index, description, png_bytes).
    """
    import io

    from PIL import Image

    def to_png(data: bytes) -> bytes:
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    out: list[tuple[int, str, bytes]] = []
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            for i in indices:
                if len(out) >= max_images:
                    break
                pix = doc[i - 1].get_pixmap(dpi=110)
                out.append((i, f"Page {i} (rendered page)", to_png(pix.tobytes("png"))))
        return out

    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(path)
    area = float(prs.slide_width * prs.slide_height)
    for i in indices:
        pics = []

        def walk(shapes):
            for sh in shapes:
                if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                    walk(sh.shapes)
                elif sh.shape_type == MSO_SHAPE_TYPE.PICTURE and sh.width and sh.height:
                    pics.append(((sh.width * sh.height) / area, sh))
        walk(prs.slides[i - 1].shapes)
        for frac, sh in sorted(pics, key=lambda x: -x[0]):
            if frac < min_area or len(out) >= max_images:
                break
            try:
                out.append((i, f"Slide {i} picture '{sh.name}' (~{frac:.0%} of slide)", to_png(sh.image.blob)))
            except Exception:  # unsupported image format (e.g. EMF) - skip, it stays flagged for manual review
                continue
    return out

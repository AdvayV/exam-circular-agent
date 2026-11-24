"""Render individual PDF pages for the model."""

from base64 import b64encode
from contextlib import closing
from io import BytesIO

from pypdfium2 import PdfDocument

from .agent import Page


def inspect_pdf_page(pdf: PdfDocument, number: int) -> Page:
    with closing(pdf[number - 1]) as page:
        scale = min(2.5, 1800 / max(page.get_size()))
        with closing(page.render(scale=scale)) as bitmap, BytesIO() as buffer:
            with bitmap.to_pil() as image:
                image.save(buffer, format="PNG")
            payload = b64encode(buffer.getvalue()).decode("ascii")
    return Page(number, f"data:image/png;base64,{payload}")

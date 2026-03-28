"""Certificate PDF generator using `assets/certificate.png` template."""

from __future__ import annotations

from datetime import date as Date
from io import BytesIO
from pathlib import Path
from typing import Union

from PIL import Image
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas


def _template_path() -> Path:
    # repo_root/app/certificates.py -> repo_root/static/images/certificate.png
    return Path(__file__).resolve().parents[1] / "static" / "images" / "certificate.png"


def _to_date_str(achieved_date: Union[Date, str]) -> str:
    if isinstance(achieved_date, str):
        return achieved_date
    return achieved_date.isoformat() if achieved_date else ""


def generate_certificate_pdf(
    user_name: str,
    level: str,
    achieved_date: Union[Date, str],
) -> bytes:
    # `level` is kept for API signature compatibility.
    _ = level

    if not user_name:
        user_name = "Learner"

    achieved_date_str = _to_date_str(achieved_date)

    buffer = BytesIO()
    page_w, page_h = landscape(letter)
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))

    template = _template_path()
    if template.exists():
        img = Image.open(template)
        img_w, img_h = img.size

        # Preserve aspect ratio while fitting inside page.
        scale = min(page_w / img_w, page_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        x0 = (page_w - draw_w) / 2
        y0 = (page_h - draw_h) / 2

        # Background template
        c.drawImage(str(template), x0, y0, width=draw_w, height=draw_h, mask="auto")

        # Template overlay positions (relative to template image 1024x723).
        # User name goes where the certificate says "awarded to:".
        name_x = x0 + draw_w / 2
        awarded_to_y = y0 + (0.52 * draw_h)
        # Mentor text goes near the bottom center.
        mentor_y = y0 + (0.82 * draw_h)

        # Draw awarded-to name (fit horizontally).
        font_size = 30
        max_width = draw_w * 0.55
        while font_size > 14 and c.stringWidth(user_name, "Helvetica-Bold", font_size) > max_width:
            font_size -= 1
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", font_size)
        c.drawCentredString(name_x, awarded_to_y, str(user_name))

        # Fixed mentor text per your request.
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(name_x, mentor_y, "GestureLab")

        # The provided `certificate.png` template doesn't include a date area,
        # so we intentionally do not render `achieved_date` here.
    else:
        # Fallback if template missing.
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(page_w / 2, page_h - 80, "Gesture Lab Certificate")
        c.setFont("Helvetica", 16)
        c.drawCentredString(page_w / 2, page_h - 130, f"Awarded to: {user_name}")
        if achieved_date_str:
            c.setFont("Helvetica", 12)
            c.drawCentredString(page_w / 2, page_h - 160, f"Achieved on: {achieved_date_str}")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()


__all__ = ["generate_certificate_pdf"]


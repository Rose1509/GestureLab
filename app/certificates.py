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


def _display_level(level: str) -> str:
    if not level:
        return "Beginner"
    low = str(level).strip().lower()
    if low == "beginner":
        return "Beginner"
    if low == "intermediate":
        return "Intermediate"
    if low in ("advance", "advanced"):
        return "Advance"
    return str(level).strip().title()


def _display_date(achieved_date: Union[Date, str]) -> str:
    if isinstance(achieved_date, Date):
        return achieved_date.strftime("%B %d, %Y")
    raw = (achieved_date or "").strip()
    if not raw:
        return ""
    # Accept YYYY-MM-DD without adding extra dependencies.
    try:
        y, m, d = raw.split("-")
        parsed = Date(int(y), int(m), int(d))
        return parsed.strftime("%B %d, %Y")
    except Exception:
        return raw


def generate_certificate_pdf(
    user_name: str,
    level: str,
    achieved_date: Union[Date, str],
) -> bytes:
    if not user_name:
        user_name = "Learner"

    level_label = _display_level(level)
    achieved_date_str = _display_date(achieved_date)

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
        # Brand text goes above printed "Mentor" area.
        mentor_y = y0 + (0.205 * draw_h)

        # Draw awarded-to name (fit horizontally).
        font_size = 30
        max_width = draw_w * 0.55
        while font_size > 14 and c.stringWidth(user_name, "Helvetica-Bold", font_size) > max_width:
            font_size -= 1
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", font_size)
        c.drawCentredString(name_x, awarded_to_y, str(user_name))

        # Clean center area and draw polished achievement message.
        msg_1 = f"Congratulations, {user_name}, on successfully completing the {level_label} level."
        msg_2 = f"You have earned the {level_label} Certificate of Achievement."
        panel_x = x0 + (0.17 * draw_w)
        panel_y = awarded_to_y - (0.225 * draw_h)
        panel_w = 0.66 * draw_w
        panel_h = 0.17 * draw_h
        c.setFillColorRGB(1, 1, 1)
        c.roundRect(panel_x, panel_y, panel_w, panel_h, 8, fill=1, stroke=0)
        c.setFillColorRGB(0.15, 0.2, 0.28)
        c.setFont("Helvetica", 14)
        c.drawCentredString(name_x, awarded_to_y - (0.103 * draw_h), msg_1)
        c.drawCentredString(name_x, awarded_to_y - (0.138 * draw_h), msg_2)

        if achieved_date_str:
            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString(name_x, awarded_to_y - (0.177 * draw_h), f"Awarded on {achieved_date_str}")

        # GestureLab branding above mentor.
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(name_x, mentor_y, "GestureLab")
    else:
        # Fallback if template missing.
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(page_w / 2, page_h - 80, "Gesture Lab Certificate")
        c.setFont("Helvetica", 16)
        c.drawCentredString(page_w / 2, page_h - 130, f"Awarded to: {user_name}")
        c.setFont("Helvetica", 12)
        c.drawCentredString(page_w / 2, page_h - 160, f"Congratulations, {user_name}, on completing the {level_label} level.")
        c.drawCentredString(page_w / 2, page_h - 178, f"You have earned the {level_label} Certificate of Achievement.")
        if achieved_date_str:
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(page_w / 2, page_h - 198, f"Awarded on: {achieved_date_str}")
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(page_w / 2, page_h - 220, "GestureLab")
        c.setFont("Helvetica", 11)
        c.drawCentredString(page_w / 2, page_h - 236, "Mentor")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()


__all__ = ["generate_certificate_pdf"]


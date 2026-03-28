# app/certificate.py – Print certificate using certificate.png layout

import os
from datetime import date
from io import BytesIO

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def _template_path():
    """Path to certificate.png template (next to static folder)."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "..", "static", "images", "certificate.png")


def generate_certificate_pdf(user_name: str, level: str, achieved_date: date) -> bytes:
    """Generate certificate PDF: certificate.png as full-page background + overlay name, date, Gesture Lab."""
    buffer = BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    template_path = _template_path()
    if os.path.isfile(template_path):
        c.drawImage(template_path, 0, 0, width=w, height=h)
    # If template missing, canvas stays white; we still draw text

    c.setFillColorRGB(0.1, 0.1, 0.1)
    cx = w / 2

    # Recipient name (centered, on the name line in the template)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(cx, h * 0.48, user_name)

    # Achievement and date (below name)
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(0.22, 0.25, 0.32)
    c.drawCentredString(cx, h * 0.40, f"For completing the {level} level quiz with a perfect score (10/10)")
    c.drawCentredString(cx, h * 0.36, f"Awarded on {achieved_date.strftime('%B %d, %Y')}")

    # "Gesture Lab" where Mentor is on the template
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(cx, h * 0.18, "Gesture Lab")

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
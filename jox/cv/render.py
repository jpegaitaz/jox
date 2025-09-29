from __future__ import annotations
from pathlib import Path
from typing import Dict
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def _write_pdf(path: Path, title: str, body: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 2*cm
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, y, title)
    y -= 1.2*cm
    c.setFont("Helvetica", 10)
    for line in body.splitlines():
        if y < 2*cm:
            c.showPage()
            y = height - 2*cm
            c.setFont("Helvetica", 10)
        c.drawString(2*cm, y, line[:110])
        y -= 0.55*cm
    c.save()

def render_cv_pdf(out_path: str | Path, job_title: str, content: str) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(p, f"{job_title} – CV", content)
    return str(p)

def render_cover_letter_pdf(out_path: str | Path, job_title: str, content: str) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(p, f"{job_title} – Cover Letter", content)
    return str(p)

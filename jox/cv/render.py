from __future__ import annotations
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer,
    ListFlowable, ListItem, HRFlowable, Table, TableStyle
)
from reportlab.lib import colors

# =========================
# Theme & Spacing
# =========================
THEMES = {
    "default": {
        "accent": colors.Color(0/255, 122/255, 98/255),        # green
        "accent_alt": colors.Color(30/255, 96/255, 166/255),   # blue
        "pill_bg": colors.Color(233/255, 247/255, 241/255),    # very light green
        "text": colors.black,
        "muted": colors.Color(0.35, 0.35, 0.35),
        "rule": colors.Color(0/255, 122/255, 98/255),
    }
}

SECTION_TOP = 14
PARA_GAP = 5
LINE_GAP = 3

# =========================
# Paragraph helpers
# =========================
def _h(text: str, theme=THEMES["default"]) -> Paragraph:
    return Paragraph(
        text.upper(),
        ParagraphStyle(
            "Heading",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            spaceBefore=SECTION_TOP,
            spaceAfter=6,
            textColor=theme["text"],
        ),
    )

def _p(text: str, size=9.7, leading=13, color=THEMES["default"]["text"]) -> Paragraph:
    return Paragraph(
        text,
        ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=size,
            leading=leading,
            spaceAfter=LINE_GAP,
            textColor=color,
        ),
    )

def _small(text: str, color=THEMES["default"]["muted"]) -> Paragraph:
    return Paragraph(
        text,
        ParagraphStyle(
            "Small",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=color,
        ),
    )

def _rule(theme=THEMES["default"]) -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=0.75,
        color=theme["rule"],
        spaceBefore=4,
        spaceAfter=8,
    )

def _bullets(items: List[str]) -> ListFlowable:
    # Proper ListFlowable API: use start for custom bullet char
    li = [ListItem(_p(i), leftIndent=8) for i in items if i]
    return ListFlowable(
        li,
        bulletType="bullet",
        start="–",                 # en-dash bullet
        leftIndent=10,
        bulletOffsetY=1,
        bulletFontName="Helvetica",
        bulletFontSize=9,
    )

# =========================
# “Pill” skills (Table-based)
# =========================
def _skills_pills(items: List[str], theme=THEMES["default"], per_row=4, max_items=8) -> Table:
    chips = [i for i in items if i][:max_items]
    if not chips:
        # Return a minimal, empty table to keep flowable type consistent
        return Table([[""]])

    rows: List[List[Paragraph]] = []
    row: List[Paragraph] = []
    for i, txt in enumerate(chips, 1):
        row.append(Paragraph(
            f"&nbsp;{txt}&nbsp;",
            ParagraphStyle(
                "Pill",
                fontName="Helvetica",
                fontSize=9,
                textColor=theme["accent_alt"],
                backColor=theme["pill_bg"],
                leading=12,
            ),
        ))
        if i % per_row == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Normalize row widths
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append(Paragraph("", ParagraphStyle("Empty", fontName="Helvetica", fontSize=9)))

    tbl = Table(
        rows,
        style=TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0, colors.white),
        ]),
        hAlign="LEFT",
    )
    return tbl

# =========================
# Header: two-zone layout (splittable, no KeepTogether)
# =========================
def _header_block(story: List[Any], header: Dict[str, str], job_title_fs: str, theme=THEMES["default"]) -> None:
    name = (header.get("name") or "").strip().upper()
    role = (header.get("tagline") or job_title_fs or "").strip()

    # Left side as a small table (splittable)
    left_rows = [
        [Paragraph(name, ParagraphStyle(
            "Name",
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=22,
            textColor=theme["text"],
        ))],
        [Paragraph(role, ParagraphStyle(
            "Role",
            fontName="Helvetica",
            fontSize=12.5,
            leading=15,
            textColor=theme["accent_alt"],
            spaceAfter=4,
        ))],
    ]
    left_table = Table(
        left_rows,
        colWidths=[104*mm],  # 104 + 70 = 174mm usable width
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        repeatRows=0,
        splitByRow=1,
    )

    # Right: contacts in 2×2 grid
    def _fmt(label: str, value: Optional[str]) -> Paragraph:
        if not value:
            return Paragraph("", ParagraphStyle("Empty", fontName="Helvetica", fontSize=9))
        return _small(f"<b>{label}:</b> {value}", color=theme["muted"])

    contacts = [
        [_fmt("City", header.get("address")), _fmt("Phone", header.get("phone"))],
        [_fmt("Email", header.get("email")), _fmt("LinkedIn", header.get("linkedin"))],
    ]
    right_table = Table(
        contacts,
        colWidths=[35*mm, 35*mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        hAlign="RIGHT",
        repeatRows=0,
        splitByRow=1,
    )

    # 2-column header (splittable row)
    header_table = Table(
        [[left_table, right_table]],
        colWidths=[104*mm, 70*mm],  # equals 174mm (A4 - 18mm*2 margins)
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        repeatRows=0,
        splitByRow=1,
    )

    story.append(header_table)
    story.append(_rule(theme))

# =========================
# Public API (unchanged signatures)
# =========================
def render_cv_pdf(path: str, job_title_fs: str, text_or_structured: Any) -> None:
    """
    Backwards-compatible wrapper: if dict -> structured template; else write plain.
    """
    if isinstance(text_or_structured, dict):
        render_cv_pdf_structured(path, job_title_fs, text_or_structured)
        return
    # legacy fallback
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica", 10)
    textobject = c.beginText(20 * mm, 280 * mm)
    for line in str(text_or_structured).splitlines():
        textobject.textLine(line)
    c.drawText(textobject)
    c.showPage()
    c.save()

def render_cv_pdf_structured(path: str, job_title_fs: str, data: Dict[str, Any]) -> None:
    theme = THEMES["default"]
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
        allowSplitting=True,  # ensure flowables can break across pages
    )
    story: List[Any] = []

    # Header
    _header_block(story, data.get("header", {}), job_title_fs, theme)

    # ===== Page 1 focus =====
    # Profile (keep brief)
    profile = (data.get("profile") or data.get("summary") or "").strip()
    if profile:
        story.append(_h("Profile", theme))
        story.append(_p(profile))

    # Core skills as pills (6–8 items max)
    core_groups = data.get("core_skills") or []
    first_group_items: List[str] = []
    if core_groups:
        g0 = core_groups[0] or {}
        first_group_items = list((g0.get("bullets") or []))[:8]
    if first_group_items:
        story.append(Spacer(1, 6))
        story.append(_skills_pills(first_group_items, theme, per_row=4, max_items=8))

    # Separator before Experience
    story.append(_rule(theme))

    # Experience (compact)
    exp = data.get("experience") or []
    if exp:
        story.append(_h("Experience", theme))
        for e in exp:
            header_bits = [s for s in [
                f"<b>{(e.get('company') or '').strip()}</b>",
                (e.get("role") or "").strip(),
                (e.get("location") or "").strip(),
                (e.get("dates") or "").strip(),
            ] if s]
            story.append(_p(" &#183; ".join(header_bits)))  # middot separators
            bullets = e.get("bullets") or []
            if bullets:
                story.append(_bullets(bullets[:3]))  # 3 bullets max on page-1
            story.append(Spacer(1, PARA_GAP))

    # ===== Page 2 (depth sections) =====
    story.append(_rule(theme))

    # Earlier Experience
    early = data.get("earlier_experience") or []
    if early:
        story.append(_h("Earlier Experience", theme))
        for e in early:
            header = " &#183; ".join([s for s in [
                (e.get("role") or "").strip(),
                (e.get("company") or "").strip(),
                (e.get("location") or "").strip(),
                (e.get("dates") or "").strip(),
            ] if s])
            story.append(_p(header))
            txt = (e.get("summary") or "").strip()
            if txt:
                story.append(_p(txt))
        story.append(Spacer(1, PARA_GAP))

    # Education (single-line entries)
    edu = data.get("education") or []
    if edu:
        story.append(_h("Education", theme))
        for e in edu:
            line = " &#183; ".join([s for s in [
                (e.get("degree") or "").strip(),
                (e.get("school") or "").strip(),
                (e.get("country") or "").strip(),
                (e.get("dates") or "").strip(),
            ] if s])
            story.append(_p(line))
        story.append(Spacer(1, PARA_GAP))

    # Certifications
    certs = data.get("certifications") or []
    if certs:
        story.append(_h("Certifications", theme))
        story.append(_bullets([c for c in certs if c]))
        story.append(Spacer(1, PARA_GAP))

    # Languages
    langs = [l for l in (data.get("languages") or []) if l]
    if langs:
        story.append(_h("Languages", theme))
        story.append(_p(", ".join(langs)))
        story.append(Spacer(1, PARA_GAP))

    # Technical & Tools (dedupe + alpha)
    tools = [t.strip() for t in (data.get("tech_tools") or []) if t and t.strip()]
    if tools:
        uniq_tools = sorted(set(tools), key=str.lower)
        story.append(_h("Technical & Tools", theme))
        story.append(_p(", ".join(uniq_tools)))
        story.append(Spacer(1, PARA_GAP))

    # Affiliations
    aff = [a for a in (data.get("affiliations") or []) if a]
    if aff:
        story.append(_h("Affiliations", theme))
        story.append(_p(", ".join(aff)))
        story.append(Spacer(1, PARA_GAP))

    # Volunteering
    vol = [v for v in (data.get("volunteering") or []) if v]
    if vol:
        story.append(_h("Volunteering", theme))
        story.append(_p(", ".join(vol)))
        story.append(Spacer(1, PARA_GAP))

    # Interests
    interests = [i for i in (data.get("interests") or []) if i]
    if interests:
        story.append(_h("Interests", theme))
        story.append(_p(", ".join(interests)))

    doc.build(story)

# =========================
# Cover Letter (unchanged signature, cleaner spacing)
# =========================
def render_cover_letter_pdf(path: str, _job_title_fs: str, text_or_structured: Any) -> None:
    """
    Backwards-compatible wrapper. If dict -> structured letter layout mirroring the sample.
    """
    if isinstance(text_or_structured, dict):
        render_cover_letter_pdf_structured(path, text_or_structured)
        return

    # legacy fallback
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica", 11)
    textobject = c.beginText(20 * mm, 280 * mm)
    for line in str(text_or_structured).splitlines():
        textobject.textLine(line)
    c.drawText(textobject)
    c.showPage()
    c.save()

def render_cover_letter_pdf_structured(path: str, data: Dict[str, Any]) -> None:
    """
    Layout: sender address (left), recipient (indented), place/date, subject, salutation,
            paragraphs, closing, signature.
    """
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=22*mm, rightMargin=22*mm, topMargin=20*mm, bottomMargin=20*mm
    )
    story: List[Any] = []

    sender = data.get("sender", {})
    recipient = data.get("recipient", {})

    # Addresses
    s_lines = [sender.get("name")] + (sender.get("address_lines") or [])
    r_lines = [recipient.get("company"), recipient.get("attention")] + (recipient.get("address_lines") or [])
    story.append(_small("<br/>".join(filter(None, s_lines))))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" + "<br/>".join(filter(None, r_lines)),
        ParagraphStyle("Rec", fontName="Helvetica", fontSize=9, leading=12),
    ))
    story.append(Spacer(1, 8))

    # Place & date
    pad = data.get("place_and_date", "")
    if pad:
        story.append(_p(pad))
        story.append(Spacer(1, 6))

    # Subject
    subj = data.get("subject", "")
    if subj:
        story.append(_p(f"<b>Subject: {subj}</b>"))
        story.append(Spacer(1, 6))

    # Salutation + paragraphs
    sal = data.get("salutation", "")
    if sal:
        story.append(_p(sal))
        story.append(Spacer(1, 4))

    for par in data.get("paragraphs", []):
        story.append(_p(par))
        story.append(Spacer(1, 4))

    # Closing + signature (separate lines, no accidental concatenation)
    clos = data.get("closing", "Kind regards,")
    story.append(Spacer(1, 6))
    story.append(_p(clos))
    story.append(Spacer(1, 8))
    story.append(_p(data.get("signature_name", sender.get("name", ""))))

    doc.build(story)

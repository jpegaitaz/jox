from __future__ import annotations
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, KeepTogether, ListFlowable, ListItem, HRFlowable
from reportlab.lib import colors

# ---------- Helpers ----------
def _h(text: str) -> Paragraph:
    return Paragraph(text, ParagraphStyle(
        "Heading",
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.black,
        underlineWidth=0.3,
        underlineOffset=-2,
    ))

def _p(text: str, size=9.7, leading=13) -> Paragraph:
    return Paragraph(text, ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=size,
        leading=leading,
        spaceAfter=2,
    ))

def _small(text: str) -> Paragraph:
    return Paragraph(text, ParagraphStyle(
        "Small",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    ))

def _sep() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceBefore=6, spaceAfter=6)

def _bullets(items: List[str]) -> ListFlowable:
    li = [ListItem(_p(i), leftIndent=0) for i in items if i]
    return ListFlowable(li, bulletType="bullet", start="•", leftIndent=10, bulletFontName="Helvetica", bulletFontSize=10)

def _header_block(story: List, header: Dict[str, str]) -> None:
    name = header.get("name", "").upper()
    tagline = header.get("tagline", "")
    contacts = " • ".join([s for s in [
        header.get("address"), f"Phone: {header.get('phone')}" if header.get("phone") else None,
        f"Email: {header.get('email')}" if header.get("email") else None,
        f"Linkedin: {header.get('linkedin')}" if header.get("linkedin") else None,
    ] if s])

    nat_mob = " • ".join([s for s in [
        f"Nationality: {header.get('nationality')}" if header.get("nationality") else None,
        f"Mobility: {header.get('mobility')}" if header.get("mobility") else None,
    ] if s])

    story.append(Paragraph(name, ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=TA_CENTER)))
    if tagline:
        story.append(Paragraph(tagline, ParagraphStyle("Tag", fontName="Helvetica-Bold", fontSize=11.5, leading=14, alignment=TA_CENTER)))
    if contacts:
        story.append(Paragraph(contacts, ParagraphStyle("Contacts", fontName="Helvetica", fontSize=9.5, leading=12, alignment=TA_CENTER)))
    if nat_mob:
        story.append(Paragraph(nat_mob, ParagraphStyle("Nat", fontName="Helvetica", fontSize=9.5, leading=12, alignment=TA_CENTER)))
    story.append(Spacer(1, 6))

def render_cv_pdf(path: str, _title: str, text_or_structured: Any) -> None:
    """
    Backwards-compatible wrapper: if dict -> structured template; else write plain.
    """
    if isinstance(text_or_structured, dict):
        render_cv_pdf_structured(path, text_or_structured)
        return
    # fallback legacy (simple dump)
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica", 10)
    textobject = c.beginText(20 * mm, 280 * mm)
    for line in str(text_or_structured).splitlines():
        textobject.textLine(line)
    c.drawText(textobject)
    c.showPage()
    c.save()

def render_cv_pdf_structured(path: str, data: Dict[str, Any]) -> None:
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    story: List[Any] = []

    _header_block(story, data.get("header", {}))

    # Profile
    profile = data.get("profile")
    if profile:
        story.append(_h("Profile"))
        story.append(_p(profile))
        story.append(_sep())

    # Core Skills
    core = data.get("core_skills") or []
    if core:
        story.append(_h("Core Skills"))
        for group in core:
            head = group.get("heading")
            if head:
                story.append(_p(f"<b>★ {head}</b>"))
            items = group.get("bullets") or []
            story.append(_bullets(items))
        story.append(_sep())

    # Experience
    exp = data.get("experience") or []
    if exp:
        story.append(_h("Experience"))
        for e in exp:
            header = " • ".join([s for s in [
                f"<b>{e.get('company','')}</b>",
                e.get("role"),
                e.get("location")
            ] if s])
            dates = e.get("dates", "")
            story.append(_p(f"{header} • {dates}"))
            bullets = e.get("bullets") or []
            story.append(_bullets(bullets))
        story.append(_sep())

    # Earlier Experience
    early = data.get("earlier_experience") or []
    if early:
        story.append(_h("Earlier Experience"))
        for e in early:
            header = " • ".join([s for s in [
                e.get("role"), e.get("company"), e.get("location"), e.get("dates")
            ] if s])
            txt = e.get("summary", "")
            story.append(_p(f"{header}"))
            if txt:
                story.append(_p(txt))
        story.append(_sep())

    # Education
    edu = data.get("education") or []
    if edu:
        story.append(_h("Education"))
        for e in edu:
            line = " • ".join([s for s in [
                e.get("degree"), e.get("school"), e.get("country"), e.get("dates")
            ] if s])
            story.append(_p(line))
        story.append(_sep())

    # Certifications
    certs = data.get("certifications") or []
    if certs:
        story.append(_h("Certifications"))
        story.append(_bullets(certs))
        story.append(_sep())

    # Languages
    langs = data.get("languages") or []
    if langs:
        story.append(_h("Languages"))
        story.append(_p(" • ".join(langs)))
        story.append(_sep())

    # Technical & Tools
    tools = data.get("tech_tools") or []
    if tools:
        story.append(_h("Technical & Tools"))
        story.append(_p(" • ".join(tools)))
        story.append(_sep())

    # Affiliations
    aff = data.get("affiliations") or []
    if aff:
        story.append(_h("Affiliations"))
        story.append(_p(" • ".join(aff)))
        story.append(_sep())

    # Volunteering
    vol = data.get("volunteering") or []
    if vol:
        story.append(_h("Volunteering"))
        story.append(_p(" • ".join(vol)))
        story.append(_sep())

    # Interests
    interests = data.get("interests") or []
    if interests:
        story.append(_h("Interests"))
        story.append(_p(" • ".join(interests)))

    doc.build(story)


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
    # Layout: applicant address (left), recipient address (indented), place & date,
    # Subject line, salutation, paragraphs, closing + signature.
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=22*mm, rightMargin=22*mm, topMargin=20*mm, bottomMargin=20*mm)
    story: List[Any] = []

    sender = data.get("sender", {})
    recipient = data.get("recipient", {})

    # Addresses
    s_lines = [sender.get("name")] + (sender.get("address_lines") or [])
    r_lines = [recipient.get("company"), recipient.get("attention")] + (recipient.get("address_lines") or [])
    story.append(_small("<br/>".join(filter(None, s_lines))))
    # recipient slightly indented to mimic sample
    story.append(Spacer(1, 2))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" + "<br/>".join(filter(None, r_lines)), ParagraphStyle("Rec", fontName="Helvetica", fontSize=9, leading=12)))
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

    # Closing
    clos = data.get("closing", "Kind regards,")
    story.append(Spacer(1, 6))
    story.append(_p(clos))
    story.append(Spacer(1, 8))
    story.append(_p(data.get("signature_name", sender.get("name", ""))))

    doc.build(story)

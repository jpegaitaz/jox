from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List

def extract_text(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() == ".pdf":
        from pdfminer.high_level import extract_text as pdf_extract
        return pdf_extract(str(p))
    if p.suffix.lower() in (".docx", ".doc"):
        from docx import Document
        doc = Document(str(p))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)
    raise ValueError("Unsupported CV format. Use PDF or DOCX.")

def naive_fields(text: str) -> Dict[str, Any]:
    # Extremely basic signal extraction
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = lines[0] if lines else "Unknown"
    skills = []
    for l in lines:
        if l.lower().startswith("skills") or "skills:" in l.lower():
            skills.extend([s.strip() for s in l.split(":")[-1].split(",")])
    return {"name": name, "skills": list(dict.fromkeys(skills)), "raw": text}

def parse_cv(path: str | Path) -> Dict[str, Any]:
    text = extract_text(path)
    fields = naive_fields(text)
    fields["source_path"] = str(path)
    return fields

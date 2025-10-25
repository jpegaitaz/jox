# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import List
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer

def extract_text_from_pdf(path: str) -> List[str]:
    pages: List[str] = []
    for page_layout in extract_pages(path):
        buf: List[str] = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                buf.append(element.get_text())
        pages.append("".join(buf).strip())
    return pages

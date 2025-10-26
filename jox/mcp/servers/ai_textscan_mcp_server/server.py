# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import logging
from typing import Any, Dict, List

from fastmcp import FastMCP
from .text_extract import extract_text_from_pdf
from .detector import analyze_text, humanize_text

logger = logging.getLogger(__name__)

def create_app() -> FastMCP:
    app = FastMCP("ai-textscan")

    @app.tool()
    async def analyze_pdf_ai_likeness(path: str) -> Dict[str, Any]:
        """
        Analyze a PDF and estimate % AI-written text with an ensemble of methods.
        Returns: { overall: {...}, pages: [...], chunks: [...], methods: {...} }
        """
        text_pages = extract_text_from_pdf(path)
        full_text = "\n\n".join(text_pages)
        result = await analyze_text(full_text, page_texts=text_pages)
        return result

    @app.tool()
    async def analyze_text_ai_likeness(text: str) -> Dict[str, Any]:
        """
        Analyze raw text for AI-likeness. Returns same schema as analyze_pdf_ai_likeness.
        """
        return await analyze_text(text)

    @app.tool()
    async def rewrite_more_human(text: str, target_percent: int = 35) -> Dict[str, Any]:
        """
        Heuristically rewrites text to reduce AI-likeness signals while preserving meaning.
        Returns: { original_percent, new_percent_estimate, rewritten_text }
        """
        rewritten = humanize_text(text, target_percent=target_percent)
        # quick re-check
        check = await analyze_text(rewritten)
        return {
            "original_percent": (await analyze_text(text))["overall"]["ai_likeness_percent"],
            "new_percent_estimate": check["overall"]["ai_likeness_percent"],
            "rewritten_text": rewritten,
        }

    return app

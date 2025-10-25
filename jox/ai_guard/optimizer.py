# jox/ai_guard/optimizer.py
from __future__ import annotations
from typing import Tuple, Dict, List, NamedTuple, Optional
import logging
import re

from .evaluator import evaluate_ai_likeness

logger = logging.getLogger("jox.ai_guard.optimizer")


# ---------- logging structures ----------

class IterLog(NamedTuple):
    iter: int
    score: float
    note: Optional[str] = None


# ---------- de-cliché + neutral expansion ----------

_MIN_EXPAND_CHARS = 140      # expand to exceed this length when text is too short
_TARGET_EXPAND_CHARS = 200   # soft target to avoid bloating

# very common CL / CV boilerplate → calmer alternatives
_CLICHE_SWAPS = {
    r"\bI am thrilled\b": "I’m interested",
    r"\bI am excited\b": "I’m interested",
    r"\bI would love\b": "I’d welcome",
    r"\bfast-paced\b": "busy",
    r"\bleverage\b": "use",
    r"\bimpactful\b": "useful",
    r"\bpassionate\b": "serious",
    r"\bresults[- ]driven\b": "focused on outcomes",
    r"\bsynergy\b": "collaboration",
    r"\bstrategic\b": "long-term",
    r"\bcutting[- ]edge\b": "modern",
    r"\butilize\b": "use",
    r"\bproven track record\b": "history of delivering",
    r"\bstrong communication skills\b": "clear, concise communication",
    r"\bresponsible for\b": "I led",
    r"\bin charge of\b": "I owned",
}

# Neutral “evidence scaffolds” to expand text without inventing facts.
# We reuse words already present in the text via _pick_hints; no numbers/names are created.
_EXPANSION_TEMPLATES = [
    " In practice, that means I {verb_hint} {object_hint} with attention to {detail_hint}.",
    " I prefer concrete steps — defining the scope, setting a simple plan, and adjusting based on feedback.",
    " I keep it readable: short updates, a clear call-to-action, and timelines people can accept.",
    " I’m careful to avoid generic claims and instead reference the responsibilities in the posting.",
    " I focus on the essentials first, then add context only where it helps a decision.",
]


def _pick_hints(text: str) -> dict:
    """Pull light-weight hints from the existing text to fill templates without inventing facts."""
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
    verbs = [w for w in words if w.lower() in {
        "build","lead","own","drive","analyze","design","plan","coordinate",
        "sell","negotiate","optimize","improve","support","manage","deliver","research"
    }]
    nouns = [w for w in words if w.lower() in {
        "pipeline","accounts","clients","team","roadmap","process","reporting",
        "pricing","strategy","product","deal","portfolio","data","model","market","partners"
    }]
    details = [w for w in words if w.lower() in {
        "quality","timelines","costs","risk","compliance","privacy","accuracy",
        "clarity","scope","feedback","learning","handover","handoffs"
    }]

    def _first_or(default):
        def _inner(arr): return arr[0] if arr else default
        return _inner

    return {
        "verb_hint": _first_or("work on")(verbs),
        "object_hint": _first_or("the work")(nouns),
        "detail_hint": _first_or("clarity")(details),
    }


def _decliche(text: str) -> str:
    out = text
    for pat, repl in _CLICHE_SWAPS.items():
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def _vary_cadence(text: str) -> str:
    """
    Aim for human rhythm:
      - merge ultra-short sentences
      - split very long ones once at comma/semicolon, if present
    """
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    sents = [s.strip() for s in sents if s.strip()]
    if not sents:
        return text

    # Merge tiny sentences into neighbors
    merged: List[str] = []
    buf = ""
    for s in sents:
        if len(s) < 40:
            buf = (f"{buf} {s}".strip()) if buf else s
        else:
            if buf:
                merged.append(buf)
                buf = ""
            merged.append(s)
    if buf:
        merged.append(buf)

    # Split very long sentences once
    balanced: List[str] = []
    for s in merged:
        if len(s) > 180:
            parts = re.split(r"(?:,|;)\s+", s, maxsplit=1)
            balanced.extend(parts if len(parts) == 2 else [s])
        else:
            balanced.append(s)

    return " ".join(balanced)


def _expand(text: str, target_len: int = _TARGET_EXPAND_CHARS) -> str:
    """
    Expand neutrally using templates + hints drawn only from the existing text.
    Avoids adding achievements, names, or numbers.
    """
    if len(text) >= target_len:
        return text
    hints = _pick_hints(text)
    out = text
    for tpl in _EXPANSION_TEMPLATES:
        if len(out) >= target_len:
            break
        out = (out.rstrip() + tpl.format(**hints)).strip()
    return out


def _humanize_pass(text: str, iteration: int) -> str:
    """
    One pass:
      1) remove clichés
      2) vary cadence
      3) if very short, EXPAND to exceed _MIN_EXPAND_CHARS (target ~140 chars)
    """
    before = text
    after = _decliche(before)
    after = _vary_cadence(after)

    if len(after) < _MIN_EXPAND_CHARS:
        expanded = _expand(after, _TARGET_EXPAND_CHARS)
        if len(expanded) > len(after):
            logger.info(
                "AI-Guard | expand | iter %d | expanded %d→%d chars",
                iteration, len(after), len(expanded)
            )
        after = expanded

    return after


# ---------- public API ----------

def reduce_ai_likeness(
    text: str,
    *,
    target_pct: int | None = None,
    max_iters: int | None = None,
    label: str | None = None,
) -> Tuple[str, Dict[str, List[Dict[str, float | int | str]]]]:
    """
    Public API used by orchestrator:
      - returns (optimized_text, log_dict)
      - logs progress with logger name 'jox.ai_guard.optimizer'
    """
    target = 35 if target_pct is None else int(target_pct)
    iters = 3 if max_iters is None else int(max_iters)

    baseline = evaluate_ai_likeness(text)
    name = label or "text"
    logger.info("AI-Guard | %s | baseline=%.1f%%", name, baseline)

    logs: List[IterLog] = [IterLog(iter=0, score=baseline, note="baseline")]
    current = text
    best_text = current
    best_score = baseline

    for i in range(1, iters + 1):
        if best_score <= target:
            break
        candidate = _humanize_pass(current, i)
        score = evaluate_ai_likeness(candidate)
        logger.info(
            "AI-Guard | %s | iter %d → %.1f%% (target ≤ %d%%)",
            name, i, score, target
        )
        logs.append(IterLog(iter=i, score=score))

        if score < best_score:
            best_score, best_text = score, candidate
        current = candidate

    serial_logs = [
        {"iter": l.iter, "score": float(l.score), "note": l.note or ""}
        for l in logs
    ]
    return best_text, {
        "label": name,
        "target": target,
        "max_iters": iters,
        "runs": serial_logs,
    }

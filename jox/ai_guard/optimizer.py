# jox/ai_guard/optimizer.py
from __future__ import annotations
from typing import Tuple, Dict, List, NamedTuple, Optional
import logging
import re
import random

from .evaluator import evaluate_ai_likeness

logger = logging.getLogger("jox.ai_guard.optimizer")


# ---------- logging structures ----------

class IterLog(NamedTuple):
    iter: int
    score: float
    note: Optional[str] = None


# ---------- de-cliché + neutral expansion (with signature awareness) ----------

# When a block is very short, expand it a bit to break template-y shapes.
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

# stylistic nudge: contractions + soft adverb pruning
_CONTRACTIONS = {
    r"\bI am\b": "I’m",
    r"\bI have\b": "I’ve",
    r"\bI will\b": "I’ll",
    r"\bI would\b": "I’d",
    r"\bwe are\b": "we’re",
    r"\bwe have\b": "we’ve",
    r"\bwe will\b": "we’ll",
    r"\bdo not\b": "don’t",
    r"\bcan not\b": "can’t",
    r"\bcannot\b": "can’t",
    r"\bis not\b": "isn’t",
    r"\bare not\b": "aren’t",
}
_COMMON_ADVERBS = r"\b(really|highly|extremely|very|deeply|truly|significantly)\b"

# 🔒 Remove/guard against the specific boilerplate that kept appearing
_STOCK_BOILERPLATE_PAT = re.compile(
    r"In practice, that means I .*?timelines people can accept\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Neutral “evidence scaffolds” to expand text without inventing facts.
# Trimmed: we removed the “In practice…” sentence entirely.
_EXPANSION_TEMPLATES = [
    " I prefer concrete steps — define the scope, set a simple plan, and adjust with feedback.",
    " I focus on essentials first and add context only when it helps a decision.",
]

# Small pragmatic next-step cues (detectors often reward these; still neutral)
_NEXT_STEP_TPLS = [
    " If helpful, I can share a brief example of {object_hint} this week.",
    " Happy to outline a simple plan and timelines in a short call.",
    " If useful, I can send a concise note on how I’d {verb_hint} {object_hint}.",
]

# Detect the start of a signature/valediction block (don’t expand after this).
_SIG_PAT = re.compile(
    r"(?im)^\s*(?:kind regards|best regards|regards|sincerely|yours truly|"
    r"yours faithfully|cordially|respectfully|with thanks|many thanks)\s*,?\s*$"
)


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


def _contractionize(text: str) -> str:
    out = text
    for pat, repl in _CONTRACTIONS.items():
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def _trim_adverbs(text: str) -> str:
    # soft prune stacked amplifiers (e.g., "really very" -> "very")
    return re.sub(fr"(?:{_COMMON_ADVERBS})(\s+{_COMMON_ADVERBS})+", r"\1", text, flags=re.IGNORECASE)


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


def _split_before_signature(text: str) -> tuple[str, str]:
    """
    Return (main, signature_block). If a valediction like 'Kind regards,' is found,
    everything from that line onward is considered the signature block.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _SIG_PAT.match(line.strip()):
            return "\n".join(lines[:i]).rstrip(), "\n".join(lines[i:]).lstrip()
    return text, ""  # no signature found


def _rejoin_with_signature(main: str, sig: str) -> str:
    return (main.rstrip() + "\n\n" + sig.lstrip()).strip() if sig else main


def _expand(text: str, target_len: int, *, allow_templates: bool) -> str:
    """
    Expand neutrally using templates + hints drawn only from the existing text.
    Avoids adding achievements, names, or numbers.
    Can be disabled (e.g., for CL:closing/intro).
    """
    if len(text) >= target_len or not allow_templates:
        return text
    hints = _pick_hints(text)
    out = text
    for tpl in _EXPANSION_TEMPLATES:
        if len(out) >= target_len:
            break
        out = (out.rstrip() + " " + tpl.format(**hints)).strip()
    # Optionally add one pragmatic next-step
    if len(out) < target_len - 20 and _NEXT_STEP_TPLS:
        out = (out.rstrip() + " " + random.choice(_NEXT_STEP_TPLS).format(**hints)).strip()
    return out


def _humanize_pass(text: str, iteration: int, *, allow_templates: bool) -> str:
    """
    One pass:
      1) split off signature/valediction
      2) de-cliché → contractions → adverb trim → cadence on the main body
      3) strip residual stock boilerplate
      4) if short, EXPAND the main body (signature stays untouched; can be disabled)
      5) re-join with signature
    """
    main, sig = _split_before_signature(text)

    after = _decliche(main)
    after = _contractionize(after)
    after = _trim_adverbs(after)
    after = _vary_cadence(after)

    # strip any residual stock boilerplate, just in case
    after = _STOCK_BOILERPLATE_PAT.sub("", after).strip()

    if len(after) < _MIN_EXPAND_CHARS:
        expanded = _expand(after, _TARGET_EXPAND_CHARS, allow_templates=allow_templates)
        if len(expanded) > len(after):
            logger.info(
                "AI-Guard | expand | iter %d | expanded %d→%d chars",
                iteration, len(after), len(expanded)
            )
        after = expanded

    return _rejoin_with_signature(after, sig)


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

    # 🔒 Disable templates for CL:closing and CL:intro to avoid boilerplate in sign-off/openers
    lower_label = (label or "").lower()
    allow_templates = not (lower_label.startswith("cl:closing") or lower_label.startswith("cl:intro"))

    logs: List[IterLog] = [IterLog(iter=0, score=baseline, note="baseline")]
    current = text
    best_text = current
    best_score = baseline

    for i in range(1, iters + 1):
        if best_score <= target:
            break
        candidate = _humanize_pass(current, i, allow_templates=allow_templates)
        score = evaluate_ai_likeness(candidate)
        logger.info("AI-Guard | %s | iter %d → %.1f%% (target ≤ %d%%)", name, i, score, target)
        logs.append(IterLog(iter=i, score=score))

        # keep the best seen
        if score < best_score:
            best_score, best_text = score, candidate
        current = candidate

    serial_logs = [{"iter": l.iter, "score": float(l.score), "note": l.note or ""} for l in logs]
    return best_text, {"label": name, "target": target, "max_iters": iters, "runs": serial_logs}

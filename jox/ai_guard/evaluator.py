# jox/ai_guard/evaluator.py
from __future__ import annotations
import math
import re
from collections import Counter

# Minimal language-aware stopwords (fallbacks). No external deps.
EN_STOP = set("""
the a an to and or for of with in on at from by is are was were be been being that which who whom whose as if while
it this these those i you he she they we me my mine your yours his her hers their theirs our ours
""".split())

FR_STOP = set("""
le la les un une des et ou pour de du au aux avec dans sur par est sont était étaient être été étant que qui
ce cette ces je tu il elle nous vous ils elles moi mon ma mes ton ta tes son sa ses leur leurs notre nos votre vos
""".split())

GENERIC_PHRASES = [
    r"results[- ]driven", r"passionate about", r"dynamic (?:team player|professional)",
    r"fast[- ]paced environment", r"detail[- ]oriented", r"strong communication skills",
    r"motivated self[- ]starter", r"proven track record", r"responsible for", r"in charge of",
    r"leads? cross[- ]functional teams"
]

def _pick_stop(text: str):
    # crude FR signal
    if re.search(r"[éèêàùûôîçœ]", text.lower()):
        return FR_STOP
    # crude EN fallback
    return EN_STOP

def _tokenize(text: str):
    toks = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:'[A-Za-zÀ-ÖØ-öø-ÿ]+)?", text)
    return [t.lower() for t in toks]

def _burstiness_score(text: str) -> float:
    # Sentence-length variance: flatter = more “AI-like”
    sents = re.split(r"[.!?]+", text)
    lengths = [len(_tokenize(s)) for s in sents if s.strip()]
    if len(lengths) < 2:
        return 90.0  # too short to judge => likely templated
    mean = sum(lengths) / len(lengths)
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    # normalize to 0..100 (lower variance => higher score)
    # guard: clamp to readable range
    if var < 1:
        return 85.0
    if var > 50:
        return 30.0
    return 85.0 - (var * 1.1)  # 85 -> ~30 as variance grows

def _repetitiveness_score(text: str) -> float:
    toks = _tokenize(text)
    if len(toks) < 30:
        return 85.0  # short = likely templated -> penalize with high AI-likeness
    counts = Counter(toks)
    stop = _pick_stop(text)
    # focus on non-stopwords
    items = [(w, c) for w, c in counts.items() if w not in stop]
    if not items:
        return 80.0
    top = sorted(items, key=lambda x: x[1], reverse=True)[:8]
    total = sum(c for _, c in top)
    max_c = top[0][1]
    # higher concentration => more AI-like
    conc = max_c / max(1, total)
    # map 0..1 to 30..90
    return 30.0 + conc * 60.0

def _boilerplate_score(text: str) -> float:
    t = text.lower()
    hits = sum(1 for pat in GENERIC_PHRASES if re.search(pat, t))
    # more boilerplate -> higher AI-likeness
    if hits == 0:
        return 40.0
    if hits >= 6:
        return 95.0
    return 40.0 + hits * 10.0

def evaluate_ai_likeness(text: str) -> float:
    """
    Heuristic "AI-likeness %" in [0,100]. Higher = more likely AI-ish.
    Combines: sentence burstiness (flatness), token repetitiveness, boilerplate clichés.
    Handles short/templated segments by returning a high-but-not-always-100 score.
    """
    clean = (text or "").strip()
    if not clean:
        return 95.0
    # extremely short closings / sign-offs: don't clamp to 100, but mark high
    if len(clean) < 50:
        return 88.0

    b = _burstiness_score(clean)
    r = _repetitiveness_score(clean)
    c = _boilerplate_score(clean)

    # weighted mean (tuneable)
    score = 0.45 * b + 0.35 * r + 0.20 * c
    return float(max(0.0, min(100.0, score)))

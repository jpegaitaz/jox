# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import math, re, statistics
from typing import Any, Dict, List, Tuple, Optional
import numpy as np
import regex as rgx

# HuggingFace GPT-2
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ---------- Model (lazy) ----------
_tokenizer = None
_model = None

def _get_model():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        name = "gpt2"  # small & fast
        _tokenizer = AutoTokenizer.from_pretrained(name)
        _model = AutoModelForCausalLM.from_pretrained(name)
        _model.eval()
        if torch.cuda.is_available():
            _model.to("cuda")
    return _tokenizer, _model

# ---------- Chunking ----------
def _split_into_chunks(text: str, max_tokens: int = 300) -> List[str]:
    # split by paragraphs, then merge to roughly max_tokens via rough word count
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    cur: List[str] = []
    cur_tokens = 0
    for p in paras:
        est = max(1, len(p.split()))
        if cur and cur_tokens + est > max_tokens:
            chunks.append("\n\n".join(cur))
            cur, cur_tokens = [], 0
        cur.append(p)
        cur_tokens += est
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks

# ---------- Perplexity & GLTR-ish ----------
@torch.inference_mode()
def _token_logprobs(text: str) -> List[float]:
    tok, mdl = _get_model()
    ids = tok(text, return_tensors="pt", truncation=True, max_length=1024)
    if torch.cuda.is_available():
        ids = {k: v.to("cuda") for k,v in ids.items()}
    out = mdl(**ids, labels=ids["input_ids"])
    # Get per-token negative log-likelihoods (shifted)
    # We approximate via loss per token if needed; for GLTR-ish ranks, do next-token logits
    logits = out.logits[:, :-1, :]           # [B, T-1, V]
    labels = ids["input_ids"][:, 1:]         # [B, T-1]
    logprobs = torch.log_softmax(logits, dim=-1)
    lp = logprobs.gather(-1, labels.unsqueeze(-1)).squeeze(-1)  # [B, T-1]
    return lp[0].detach().float().cpu().tolist()

@torch.inference_mode()
def _token_ranks(text: str) -> List[int]:
    tok, mdl = _get_model()
    ids = tok(text, return_tensors="pt", truncation=True, max_length=1024)
    if torch.cuda.is_available():
        ids = {k: v.to("cuda") for k,v in ids.items()}
    out = mdl(**ids)
    logits = out.logits[:, :-1, :]                    # next-token logits
    next_ids = ids["input_ids"][:, 1:]
    ranks: List[int] = []
    topk = torch.topk(logits, k=50, dim=-1)           # top-50 ranks coverage
    top_idx = topk.indices
    for t in range(next_ids.shape[1]):
        gold = next_ids[0, t].item()
        # find gold in sorted top list
        pos = (top_idx[0, t] == gold).nonzero(as_tuple=False)
        if pos.numel() > 0:
            ranks.append(int(pos[0].item()) + 1)      # 1..50
        else:
            ranks.append(1000)                        # >50 bucket
    return ranks

def _perplexity(logprobs: List[float]) -> float:
    # ppl = exp(-mean logprob)
    return float(math.exp(-sum(logprobs)/max(1,len(logprobs))))

def _burstiness(logprobs: List[float]) -> float:
    # variance (or stdev) of logprobs; higher variance → more human-like
    if len(logprobs) < 2:
        return 0.0
    return float(statistics.pstdev(logprobs))

def _gltr_bins(ranks: List[int]) -> Dict[str, float]:
    # GLTR-like: fraction of tokens in top-10 / 100+ ranks, etc.
    n = max(1, len(ranks))
    top10 = sum(1 for r in ranks if r <= 10) / n
    top50 = sum(1 for r in ranks if r <= 50) / n
    over50 = sum(1 for r in ranks if r > 50) / n
    return {"top10": top10, "top50": top50, "over50": over50}

# ---------- Stylometry ----------
_FUNCWORDS = {
    "the","and","or","but","if","while","as","of","in","on","for","to","with","by","from","that","which","who","whom","whose"
}
def _stylometry(text: str) -> Dict[str, float]:
    sents = rgx.split(r"(?<=[.!?])\s+", text.strip())
    words = re.findall(r"[A-Za-z’']+", text)
    wlen = [len(w) for w in words] or [1]
    slen = [len(s.split()) for s in sents if s.strip()] or [1]
    func = sum(1 for w in words if w.lower() in _FUNCWORDS)
    t = max(1, len(words))
    punct_div = len(set(re.findall(r"[^\w\s]", text)))
    unique_ratio = len(set(w.lower() for w in words)) / t
    return {
        "avg_word_len": float(sum(wlen)/len(wlen)),
        "avg_sent_len": float(sum(slen)/len(slen)),
        "sent_len_stdev": float(statistics.pstdev(slen) if len(slen) > 1 else 0.0),
        "funcword_rate": float(func / t),
        "punct_diversity": float(punct_div),
        "unique_ratio": float(unique_ratio),
    }

# ---------- Fusion & calibration ----------
def _score_chunk(text: str) -> Dict[str, Any]:
    lps = _token_logprobs(text)
    ranks = _token_ranks(text)
    ppl = _perplexity(lps)
    burst = _burstiness(lps)
    gltr = _gltr_bins(ranks)
    styl = _stylometry(text)

    # Normalize heuristics into 0..1 “AI-likeness” then fuse
    # (empirical, conservative)
    # - Lower perplexity → more likely AI (esp. < 30)
    ai_ppl = 1.0 - (min(ppl, 80.0) / 80.0)
    # - Lower burstiness → more likely AI (flat cadence)
    ai_burst = 1.0 - min(burst / 1.2, 1.0)            # 0..~1
    # - GLTR: many top-10 tokens → likely AI
    ai_gltr = min(1.0, gltr["top10"] * 1.3)           # amplify top10 share
    # - Stylometry: low sentence stdev & low punctuation diversity → AI-ish
    ai_style = 0.0
    ai_style += 0.6 * (1.0 - min(styl["sent_len_stdev"] / 8.0, 1.0))
    ai_style += 0.4 * (1.0 - min(styl["punct_diversity"] / 6.0, 1.0))

    # Weighted fusion
    weights = np.array([0.35, 0.2, 0.3, 0.15])
    vec = np.array([ai_ppl, ai_burst, ai_gltr, ai_style])
    raw = float(np.clip(np.dot(weights, vec), 0.0, 1.0))

    # Map to % with a conservative S-curve (harder to reach high %)
    percent = int(round(100 * (1 / (1 + math.exp(-4*(raw-0.55))))))
    return {
        "ai_percent": percent,
        "features": {
            "perplexity": ppl,
            "burstiness": burst,
            "gltr": gltr,
            "stylometry": styl,
            "ai_components": {
                "ppl": ai_ppl, "burst": ai_burst, "gltr": ai_gltr, "style": ai_style, "raw": raw
            }
        }
    }

async def analyze_text(text: str, page_texts: Optional[List[str]] = None) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"overall": {"ai_likeness_percent": 0}, "pages": [], "chunks": [], "methods": {}}

    # Chunk whole text
    chunks = _split_into_chunks(text, max_tokens=300)
    chunk_scores = [_score_chunk(c) for c in chunks]

    # Aggregate
    overall = int(round(sum(s["ai_percent"] for s in chunk_scores) / max(1, len(chunk_scores))))
    out: Dict[str, Any] = {
        "overall": {"ai_likeness_percent": overall},
        "chunks": [
            {"index": i, "ai_percent": s["ai_percent"], "excerpt": chunks[i][:400], "features": s["features"]}
            for i, s in enumerate(chunk_scores)
        ],
        "methods": {
            "notes": "Ensemble of GPT-2 perplexity, burstiness, GLTR-style token-rank coverage, and stylometry.",
            "model": "gpt2 (HF Transformers, local inference)",
        }
    }

    # Optional page mapping
    if page_texts:
        page_chunks: List[List[int]] = []
        # Greedy map: assign chunk i to page j by cumulative length
        lens_pages = [len(p) for p in page_texts]
        cum_pages = np.cumsum([0] + lens_pages)
        pos = 0
        page_map: List[int] = []
        for i, c in enumerate(chunks):
            start = pos
            end = pos + len(c)
            # find page index where most of chunk resides
            j = max(0, min(len(lens_pages)-1, int(np.searchsorted(cum_pages, (start+end)//2) - 1)))
            page_map.append(j)
            pos = end + 2  # account for '\n\n' stitching

        pages: List[Dict[str, Any]] = []
        for j in range(len(page_texts)):
            idxs = [i for i, pj in enumerate(page_map) if pj == j]
            if idxs:
                ai = int(round(sum(chunk_scores[i]["ai_percent"] for i in idxs)/len(idxs)))
            else:
                ai = 0
            pages.append({
                "page_index": j,
                "ai_percent": ai,
                "chunk_indexes": idxs
            })
        out["pages"] = pages

    return out

# ---------- Humanizer ----------
def humanize_text(text: str, target_percent: int = 35) -> str:
    """
    Lightweight “humanizer”:
    - vary sentence cadence (short + long)
    - introduce mild idioms and personal markers (without fluff)
    - subtle punctuation & connective variety
    - preserve meaning
    """
    if not text.strip():
        return text

    # sentence split (simple)
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    out: List[str] = []
    fillers = [
        "to be frank", "in plain terms", "for what it’s worth",
        "from hands-on experience", "for context", "as a side note"
    ]
    linkers = ["Plus", "Also", "Meanwhile", "That said", "Even so", "In practice"]

    for i, s in enumerate(sents):
        s2 = s.strip()
        if not s2:
            continue

        # vary punctuation slightly
        if len(s2) > 120 and "," not in s2:
            s2 = s2.replace(" and ", ", and ", 1)

        # insert occasional linker/filler for rhythm (not too often)
        if i % 5 == 3 and len(s2.split()) > 10:
            s2 = f"{np.random.choice(fillers).capitalize()}, {s2[0].lower()}{s2[1:]}"

        if i % 4 == 1 and len(s2.split()) < 14:
            s2 = f"{np.random.choice(linkers)} — {s2[0].lower()}{s2[1:]}"

        out.append(s2)

    # join with mixed separators
    rebuilt: List[str] = []
    for i, s in enumerate(out):
        rebuilt.append(s)
        if i < len(out)-1:
            sep = np.random.choice([" ", "  ", "\n"])
            rebuilt.append(sep)
    return "".join(rebuilt)

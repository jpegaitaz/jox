# JOX

Local, agentic job-search assistant. It orchestrates **MCP sub-agents** (vendored) to:
- search roles (Indeed first; LinkedIn optional),
- enrich & score them against your CV,
- generate a tailored **2-page CV** and **cover letter** per short-listed job.

> Terminal-first UX. All processing happens locally except LLM calls.

---

## Features

- **Indeed search** (country-aware TLD, date-window widening, city/alias sweep, `.com` fallback)
- Optional **LinkedIn** scraping via a hardened Selenium driver
- Heuristic **compatibility scoring** vs your current CV + knowledge base
- Auto-rendered **PDF CV** + **PDF cover letter** per shortlisted role
- Session report + artifacts saved under `outputs/`

---

## Quick start

```bash
cp .env.example .env
# edit .env and set at least:
#   OPENAI_API_KEY=sk-...
# Optional (only if you plan to use LinkedIn tools):
#   LINKEDIN_COOKIE='li_at=...'

# (optional) create venv
python -m venv .venv && source .venv/bin/activate

pip install -e ".[dev]"
make dev-setup

# Run the terminal UX
python -m jox.cli

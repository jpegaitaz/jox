# JOX — Command Cheat Sheet

Local, agentic job-search assistant. Terminal-first UX.  
All processing is local except LLM calls.

---

## One-time setup

```bash
# create .env in project root with:
#   OPENAI_API_KEY=sk-...
#   LINKEDIN_COOKIE=li_at=...   # optional, for LinkedIn tools

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
./scripts/dev_setup.sh   # optional helper

# 1) Run JOX (interactive)
python -m jox.cli

# 2) AI-Guard
# target percentage (lower = more aggressive) and max iterations
python -m jox.cli --ai-target 55 --ai-max-iters 3
python -m jox.cli --ai-target 50 --ai-max-iters 4
python -m jox.cli --ai-target 35 --ai-max-iters 6

# 3) Pick job source
export JOB_SOURCE=jobs      # or: indeed | jobup
python -m jox.cli

# 4) ASCII banner
# Disable the banner if you want a clean console:
export JOX_NO_BANNER=1
python -m jox.cli




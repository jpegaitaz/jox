# JOX

Local, agentic job-search assistant. Orchestrates **MCP subagents** (starting with a vendored
LinkedIn MCP server) to search roles, fetch details, compare against your CV, and generate a
tailored 2-page CV + cover letter. Terminal-first UX.

## Quick start

```bash
cp .env.example .env
# edit .env to include LINKEDIN_COOKIE='li_at=...'

# (optional) create venv
python -m venv .venv && source .venv/bin/activate

pip install -e ".[dev]"
make dev-setup

# Run the terminal UX
python -m jox.cli

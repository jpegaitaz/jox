# 

      ██╗ ██████╗ ██╗    ██╗
      ██║██╔═══██╗ ██║  ██╔╝
      ██║██║   ██║   ███╔╝
 ██   ██║██║   ██║ ██╔═ ██╗
 ╚█████╔╝╚██████╔╝██║    ██╗
  ╚════╝  ╚═════╝ ╚═╝    ╚═╝
  by DarkMatter

============================
Job Orchestrator eXpress
(search • score • tailor • guard)

JOX is a local, agentic job-search assistant that runs entirely from the terminal. It coordinates a fleet of **MCP sub-agents** to discover roles, evaluate their fit against your CV and knowledge base, and generate tailored two-page CVs, cover letters, and run summaries per shortlisted job. Optional **AI-Guard** passes rewrite generated text to sound more human while keeping facts intact. All artefacts stay on disk; outside traffic is limited to job boards and whichever LLM you configure.

---

## Why JOX

- **Job search in one loop** – scrape roles from Indeed, Jobup.ch, or Jobs.ch, enrich them, and shortlist the best matches automatically.
- **Tailored documents** – produce printable CV and cover-letter PDFs grounded in your uploaded CV and memory entries.
- **AI-likeness controls** – run iterative “humanization” passes with per-section scores and trace logs.
- **Local-first & auditable** – no remote state; session reports, artefacts, and AI-Guard traces are saved under `outputs/`.
- **Extensible architecture** – vendored MCP servers and adapters make it straightforward to add sources or detectors.

---

## Architecture Cheat Sheet

- **CLI (`jox/cli.py`)** – Typer app that shows the ASCII banner, collects prompts, loads memory, and launches workflows.
- **Workflows (`jox/workflows/`)** – `quick_and_ready` is the main orchestrated run (search → score → optimize → render). A dedicated `optimize_ai_likeness` workflow exposes AI-Guard-only passes.
- **Orchestrator (`jox/orchestrator/`)** – handles job tool calls, scoring, LLM prompting, AI-Guard integration, PDF rendering, and outcome persistence.
- **MCP Runtime (`jox/mcp/`)** – wraps vendored FastMCP servers for Indeed, Jobup, Jobs.ch, LinkedIn, and AI TextScan.
- **CV modules (`jox/cv/`)** – parse DOCX/PDF inputs, normalize structured data, and export rich PDFs.
- **Quality guards (`jox/ai_guard/`, `jox/quality/`)** – evaluate and reduce AI-likeness via heuristic rewrites and optional external detectors.
- **State & reports (`data/`, `outputs/`)** – memory entries, prior outcomes, generated PDFs, and JSON session reports live here.

```
.
├── jox/                # Application package
│   ├── cli.py          # Entry point (Typer)
│   ├── workflows/      # Workflow orchestrations
│   ├── orchestrator/   # Search, scoring, rendering
│   ├── mcp/            # Vendored MCP servers & adapters
│   ├── cv/             # CV parsing + PDF rendering
│   ├── ai_guard/       # AI-likeness optimizer
│   └── utils/, guards/ # Logging, telemetry, helpers
├── scripts/            # Dev + run helpers
├── tests/              # Pytest coverage
├── docs/               # Architecture, security, usage notes
└── outputs/            # Artefacts and reports per session
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- Google Chrome (or Chromium) for Selenium-driven job boards
- Correct `chromedriver` binary on your PATH (bundled copy lives at `./chromedriver`)

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # installs JOX + dev tooling
```

Create a `.env` file in the project root (no template is committed) with at least:

```
OPENAI_API_KEY=sk-...
# Optional, required for LinkedIn MCP tools:
LINKEDIN_COOKIE=li_at=...
```

Other useful toggles (see `jox/settings.py`):

```
JOB_SOURCE=indeed           # or jobup / jobs
COMPATIBILITY_THRESHOLD=7.5
MAX_DOCS=5
JOX_NO_BANNER=1             # skip ASCII banner
```

Run the one-time dev helper if desired:

```bash
./scripts/dev_setup.sh
```

---

## Running JOX

Launch the interactive workflow:

```bash
python -m jox.cli --workflow quick-and-ready
```

You will be prompted to:

1. Append optional memory entries (e.g., achievements or preferences).
2. Provide the path to your baseline CV (`.pdf` or `.docx`).
3. Enter target function, role title, and country/location.
4. Confirm the job source (defaults to `JOB_SOURCE` env or `indeed`).

### AI-Guard knobs
- `--ai-target 35` – aim for ≤35 % AI-likeness.
- `--ai-max-iters 4` – cap optimization passes per section.

During the run JOX will:

- Fetch listings via the chosen MCP job tool.
- Enrich them, score compatibility vs. your CV + memory, and shortlist.
- Generate structured CV and cover-letter drafts through the configured LLM.
- Optionally run AI-Guard rewrites and display a summary table.
- Render PDFs and write a session report under `outputs/`.

Outputs include:
- `outputs/artifacts/` – generated CVs and cover letters (`.pdf`).
- `outputs/reports/` – JSON session reports with raw listings, scores, and AI-Guard traces.
- `data/entries.json`, `data/outcomes.json` – cumulative memory and historical results.

---

## Quality & Tooling

- **Tests:** `pytest`
- **Linting & type checks:** `./scripts/lint.sh` (wraps Ruff + mypy)
- **Quick smoke run:** `./scripts/run_quick_and_ready.sh`

AI-Guard and detectors rely on the vendored FastMCP servers; ensure dependencies for Selenium (Chrome, driver) are available if you enable Jobup/Jobs.ch or LinkedIn tools.

---

## Helpful References

- `docs/ARCHITECTURE.md` – high-level component map.
- `docs/cheatsheet.md` – CLI walkthrough with screenshots and tips.
- `docs/SECURITY.md` – threat model, telemetry controls, and guidance on handling cookies.
- `docs/MCP_LINKEDIN_NOTES.md` – setup steps for LinkedIn MCP usage and li_at handling.

Reach out via issues or PRs if you add new sources, improve scoring heuristics, or extend AI-Guard recipes.

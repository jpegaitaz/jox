# Security

- **Secrets**: Env-only (`LINKEDIN_COOKIE`), never stored on disk.
- **Network**: MCP scraping limited to LinkedIn domains (see `guards/net_allowlist.py`).
- **Logging**: Masks `li_at` and emails.
- **Artifacts**: PDFs written under `outputs/artifacts/`.

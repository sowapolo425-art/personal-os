# Personal OS

[![Version](https://img.shields.io/badge/Version-0.4.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-8B5CF6)](docs/AGENTS.md)
[![Storage](https://img.shields.io/badge/Storage-Local%20Markdown-10B981)](docs/DATA-SPEC.md)
[![License](https://img.shields.io/badge/License-MIT-orange)](LICENSE)
[![Tests](https://github.com/sowapolo425-art/personal-os/actions/workflows/tests.yml/badge.svg)](https://github.com/sowapolo425-art/personal-os/actions/workflows/tests.yml)

Local Markdown personal data and memory tools for your existing MCP Agent.

You run the server and own the vault. No accounts, hosted storage, model calls or telemetry.
Use your own Agent and model provider. Cloud-backed Agents may send retrieved records to their provider.

## Cross-Agent memory (v0.4)

Ask your existing Agent to extract accessible conversation history into the same local vault.
Seven new MCP tools provide provenance-preserving conversation intake, stable-ID deduplication,
extraction checkpoints, evidenced insight proposals and selected-record analysis packs.
Uploaded documents, daily thoughts and events also enter the same extraction workflow.
Text PDF/DOCX, UTF-8 MD/TXT and conversation JSON imports are supported; scanned images require OCR elsewhere.
User statements, AI inferences and conflicts remain distinct through human approval.
The dashboard includes conversation progress and previewable JSON exports for your own Agent or API client.

This project does not scrape client histories, grant history access, call models or store API keys.
Actual history access depends on the client; no brand-wide history integration is certified.
See [history extraction contract](docs/HISTORY-EXTRACTION.md).

## Local dashboard (v0.2)

Run `personal-os --vault /absolute/path/to/private-vault dashboard` to open a local browser panel.
Inspect activity, records, timelines, sources and history; capture notes and review proposals.
The panel binds only to `127.0.0.1`, requires no frontend build, loads no external assets,
and refreshes every 30 seconds. Use `--no-browser` or `--port 8766` as needed.
See [dashboard guide](docs/DASHBOARD.md). Screenshots use entirely fictional data.

## Easier setup and portability (v0.3)

On Windows, unzip the repository and double-click `launch.cmd`. Python 3.11+ is required;
the first run installs dependencies and asks for a private vault folder outside the source tree.
Later launches remember the folder and can run offline. On macOS/Linux, use
`python3 scripts/launch.py`; `--choose` selects another vault and `--vault PATH` supports headless setups.

The panel imports UTF-8 MD/TXT and ChatGPT active-branch or messages JSON exports after preview,
deduplicates original text, and labels transcripts as imported sources rather than personal facts.
Imports default to restricted. Backups include all private records, proposals and history in a
plaintext ZIP with integrity hashes. Restore creates a separate adjacent vault, never overwriting
the active one. The source graph shows explicit evidence references only. The guide can generate
the running environment's MCP JSON or Codex TOML. See [portability limits](docs/PORTABILITY.md).

## Quick start

Requires Python 3.11+.

```sh
python -m venv .venv
# Use .venv/bin/python on Unix or .venv\Scripts\python.exe on Windows:
python -m pip install -e .
personal-os --vault /absolute/path/to/private-vault init
personal-os --vault /absolute/path/to/private-vault serve
```

Install inside the virtual environment; replace `python` accordingly or activate it first.
Configure your Agent to start the virtual environment's Python with
`-m personal_os.cli --vault /absolute/path/to/private-vault serve` as a **stdio MCP server**.
See [Agent configuration](docs/AGENTS.md) for JSON and Codex TOML examples.

Core tools: `capture_record`, `search_records`, `read_record`, `propose_record`.
Seven extraction/analysis tools are listed in the [history and material contract](docs/HISTORY-EXTRACTION.md).
Profile creation and all formal updates require proposals. There is no MCP approval tool.
Review with `show-proposal ID`, then `approve ID` or `reject ID`, using the same `--vault` option.
This is a workflow boundary, not protection against an Agent with unrestricted shell access.

Managed records are UTF-8 Markdown with JSON-compatible YAML frontmatter. History lives in
`.personal-os/history`; proposals live in `.personal-os/proposals`. Private records are visible
to the connected Agent; restricted records are hidden unless the human explicitly enables
`serve --allow-restricted`. Storage is plaintext. Deleting current records retains history.

Four suggested interaction modes: capture, deep discussion with authorized capture,
discussion without tool writes, and evidence-based review. These are Agent instructions,
not a server-side session state machine. AI inferences must never masquerade as user facts.

Supports clients that can launch local stdio MCP servers. Brand-level installation tests
are not yet completed for Codex, Claude Code, ZCode or WorkBuddy. SDK-level subprocess
integration is tested separately; see [verification](docs/VERIFICATION.md).

The project was inspired by interviews with Justin Sun and Shao Ailun, as described by
the project creator. No verified quotation or endorsement is claimed.

See the [Chinese README](README.md), [data specification](docs/DATA-SPEC.md),
[privacy notes](docs/PRIVACY.md), and [roadmap](docs/ROADMAP.md). MIT licensed.

# Personal OS

Local Markdown personal data and memory tools for your existing MCP Agent.

You run the server and own the vault. No accounts, hosted storage, model calls or telemetry.
Use your own Agent and model provider. Cloud-backed Agents may send retrieved records to their provider.

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

Tools: `capture_record`, `search_records`, `read_record`, `propose_record`.
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

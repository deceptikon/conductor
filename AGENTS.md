# Conductor — Agent Quick-Start

Model-agnostic agent orchestration harness. Drives headless coding CLIs through a LangGraph pipeline: Plan → Review → Human Gate → Act → QA → Commit.

Symlinked to `~/.local/bin/conductor` — runnable from any directory.

## Run the CLI

The conductor is symlinked to `~/.local/bin/conductor` and can be run from **any directory** (it delegates to `~/Q/conductor` internally).

```bash
# Dry-run graph compilation for a project (no workers invoked)
conductor selftest adlai

# Start a run (pauses at approval gate)
conductor run adlai "Add docstring to ingest_pdf" --type docs

# Start a run tied to an RVC issue — context auto-fetched
conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77

# Resume a paused run
conductor approve  <run_id>
conductor reject   <run_id> --note "use streaming parser"
conductor edit     <run_id> --plan-file revised.json

# Inspect runs
conductor status <run_id>
conductor list
conductor logs   <run_id> -f
```

## Running the Flow (Cheatsheet)

```bash
# 1. Verify config and graph wiring (dry-run, no workers)
uv run conductor selftest adlai

# 2. Start a run — pauses at the human-approval gate
uv run conductor run adlai "Add docstring to ingest_pdf" --type docs

# 3. Review the printed plan, then:
uv run conductor approve  <run_id>   # proceed to act
uv run conductor reject   <run_id> --note "reason"  # back to planner
uv run conductor edit     <run_id> --plan-file revised.json  # edit plan

# 4. Monitor / inspect
uv run conductor status <run_id>
uv run conductor logs   <run_id> -f
uv run conductor list

# 5. Background run (detached, logs to file)
uv run conductor run adlai "task" --bg
# Then approve later: uv run conductor approve <run_id>
```

**Pipeline flow:** `plan` → `review` → `approve` (human gate) → `act` → `qa` → `commit` → `end`.  
On QA failure it loops `act` → `qa` up to `max_qa_retries` (default 2), then routes to `plan_reviser`.

## Project Layout

- `conductor/__main__.py` — CLI entry point (`conductor` script).
- `conductor/pipeline.py` — LangGraph state machine (the core pipeline).
- `conductor/workers.py` — Stateless CLI adapters (`claude`, `gemini`, `qwen`, `opencode`).
- `conductor/projects_config.py` — Loads per-project TOML from `conductor/projects/<name>.toml`.
- `conductor/schema.py` — `Plan` and `TaskNode` dataclasses + validation.
- `main.py` — **Placeholder only** (ignore for harness work).
- `agentic/bridge.py` — **Unrelated narrative agent** (talks to local LLM server on `:22222`); not part of the conductor pipeline.

## Pipeline State & Resumption

- State is checkpointed to `.conductor/checkpoints.sqlite` (repo-local, not `~/.hermes`).
- Run ledgers are written to `.conductor/runs/<run_id>.json`.
- The human-approval gate uses LangGraph `interrupt()`. To resume, the CLI rebuilds the graph from the project name stored in the ledger and sends `Command(resume=...)`.

## Worker Binaries

**`opencode` and `qwen` are installed system-wide.** `claude` and `gemini` are **not** present in this workspace.

- `adlai.toml` routes all nodes to `qwen` with model-specific pinning:
  - `plan`  → `qwen` (`qwen/qwen3.7-plus`, read-only)
  - `act`   → `qwen` (`qwen/qwen3.6-plus`)
  - `bulk`  → `qwen` (`qwen/qwen3-coder-flash`)
  - `review`→ `qwen` (`qwen/qwen3.7-max`)
- `qwen` headless invocation: positional prompt + `-o stream-json` (the `-p` flag is deprecated). `--approval-mode plan` enforces read-only mode. `-m <model>` passes the model name.
- `opencode` headless invocation: `opencode run <prompt> -m <model>`. No `--approval-mode` flag exists; `read_only` is ignored for this worker.
- `create_worker(agentic, model=None, ...)` already accepts a `model` parameter — use it to pin a specific LLM per node.
- If you are testing or developing without invoking real workers, use `selftest`.

## RVC Integration

When `--issue STORY-XX` is passed to `conductor run`, the pipeline automatically fetches the issue context via `rvc context STORY-XX` and injects it into both the **plan** and **act** prompts. This gives workers the full vault context (linked specs, acceptance criteria, epic references) without manual copy-pasting.

- The `rvc` binary is resolved from PATH, with fallback to `~/.local/bin/rvc`.
- If the issue is not found or `rvc` fails, the pipeline logs a warning and continues without the extra context (never breaks the run).
- RVC context is fetched fresh on every `plan` and `act` invocation so retries always have the latest vault state.

## Logging

- Console logging (INFO, or DEBUG with `-v`) goes to stdout.
- **Per-run file logs** are written to `.conductor/logs/<run_id>.log` so later agents can inspect what earlier agents did. The file always captures DEBUG regardless of the console level.
- `uv run conductor logs <run_id>` shows the ledger **and** tails the last 8KB of the detailed log file if it exists.
- Each command handler sets up its own logging; `selftest` logs to `selftest-<project>.log`.

## Testing

- There are **no unit tests** in this repo.
- `uv run conductor selftest <project>` is the only built-in verification.
- `test_fixtures/` contains a fake repo and `qa-pass.sh` / `qa-fail.sh` shells for manual QA gate testing.

## Known Static Issues (do not re-introduce)

1. `after_approve` conditional bug: empty `rejection_note` routes to `end` instead of back to `plan`.
2. `qa_node` uses `subprocess.run(..., shell=True)` — unsafe if `qa_cmd` is ever user-controlled.
3. `plan_reviser_node` is a stub; it does not actually diagnose failures.
4. `WorkerResult.error` truncates stderr to last 2000 chars.
5. `_extract_stream_json` silently drops malformed lines.

## Config Notes

- Project TOML lives in `conductor/projects/<name>.toml`.
- `agents_md` path defaults to `<repo>/AGENTS.md` but can be overridden (ADLAI uses `~/Documents/ADLAI/CLAUDE.md`).
- `qa_cmd` is executed with `shell=True` in the `repo` directory.
- Routing fallback order: project TOML → `WORKER_CONFIG` dict → `DEFAULT_ROUTING` in `workers.py`.

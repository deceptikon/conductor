> **Active Epic:** [[epic-storywriter-contract]]

---
domain: workflow_meta
domain_tags: ["planning"]

# Conductor

Model-agnostic agent orchestration harness. Drives headless coding CLIs through a LangGraph pipeline: **Plan → Review → Human Gate → Act → QA → Commit**.

## Quick Start

The conductor is symlinked to `~/.local/bin/conductor` and can be run from **any directory**.

```bash
# Verify config and graph wiring (dry-run, no workers)
conductor selftest adlai

# Start a run — pauses at the human-approval gate
conductor run adlai "Add docstring to ingest_pdf" --type docs

# Start a run tied to an RVC issue — context auto-fetched
conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77

# Resume a paused run
conductor approve  <run_id>
conductor reject   <run_id> --note "reason"
conductor edit     <run_id> --plan-file revised.json

# Monitor / inspect
conductor status <run_id>
conductor logs   <run_id> -f
conductor list
```

**Pipeline flow:** `plan` → `review` → `approve` (human gate) → `act` → `qa` → `commit` → `end`.  
On QA failure it loops `act` → `qa` up to `max_qa_retries` (default 2), then routes to `plan_reviser`.

## Project Layout

| File | Purpose |
|------|---------|
| `conductor/__main__.py` | CLI entry point |
| `conductor/pipeline.py` | LangGraph state machine (core pipeline) |
| `conductor/workers.py` | Stateless CLI adapters (`claude`, `gemini`, `qwen`, `opencode`) |
| `conductor/projects_config.py` | Loads per-project TOML from `conductor/projects/<name>.toml` |
| `conductor/schema.py` | `Plan` and `TaskNode` dataclasses + validation |
| `conductor/projects/adlai.toml` | ADLAI project routing & config |

## Pipeline State & Resumption

- State is checkpointed to `.conductor/checkpoints.sqlite` (repo-local).
- Run ledgers are written to `.conductor/runs/<run_id>.json`.
- Per-run file logs are written to `.conductor/logs/<run_id>.log`.
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

## RVC Integration

When `--issue STORY-XX` is passed to `conductor run`, the pipeline automatically fetches the issue context via `rvc context STORY-XX` and injects it into both the **plan** and **act** prompts. This gives workers the full vault context (linked specs, acceptance criteria, epic references) without manual copy-pasting.

- The `rvc` binary is resolved from PATH, with fallback to `~/.local/bin/rvc`.
- If the issue is not found or `rvc` fails, the pipeline logs a warning and continues without the extra context (never breaks the run).
- RVC context is fetched fresh on every `plan` and `act` invocation so retries always have the latest vault state.

## Testing

- There are **no unit tests** in this repo.
- `conductor selftest <project>` is the only built-in verification.
- `test_fixtures/` contains a [[teamflow/conductor/test_fixtures/fake-repo/AGENTS|fake-repo/AGENTS.md]] and `qa-pass.sh` / `qa-fail.sh` shells for manual QA gate testing.

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



## Sub-Documents & Context
- [[conductor/00_Project/REGLAMENT]]
- [[conductor/00_Project/AGENTS]]
- [[conductor/00_Project/HANDOVER]]
- [[conductor/00_Project/OVERALL_COMMON_REPORT]]
- [[conductor/docs/flow/FLOW_DOCS_INDEX]]
- [[teamflow/conductor/10_Issues/01_To_Do/STORY-02 - Epic Gate — Pre-Planning Storywriter & Contract Creation Pipeline|STORY-02]]
- [[conductor/2026-07-01]]
- [[conductor/conductor/plans/STORY-02-manual-execution-ritual]]
- [[conductor/plans/refined-verifiable-plan-generation]]
- [[conductor/plans/refined-verifiable-plan-generation-v2]]

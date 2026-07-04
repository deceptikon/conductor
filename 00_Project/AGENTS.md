---
domain: workflow_meta
domain_tags: ["planning"]

# Conductor — Agent Quick-Start

Model-agnostic agent orchestration harness. Drives headless coding CLIs through a LangGraph pipeline: Plan → Review → Human Gate → Act → QA → Commit.

Symlinked to `~/.local/bin/conductor` — runnable from any directory.

## Run the CLI

```bash
# Dry-run graph compilation for a project (no workers invoked)
conductor selftest adlai

# Start a run — pauses at approval gate; story-only context by default
conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77

# Full vault context (issue + all linked docs, ~80K chars)
conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77 --extra-context

# Skip vault entirely (fastest)
conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77 --no-context

# No vault at all
conductor run adlai "Add docstring to ingest_pdf" --type docs

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
- `RECOMMENDATIONS.md` — Prioritized improvements with code sketches.

## Pipeline State & Resumption

- State is checkpointed to `.conductor/checkpoints.sqlite` (repo-local, not `~/.hermes`).
- Run ledgers are written to `.conductor/runs/<run_id>.json`.
- The human-approval gate uses LangGraph `interrupt()`. To resume, the CLI rebuilds the graph from the project name stored in the ledger and sends `Command(resume=...)`.
- Rejection without a note always routes back to `plan` (fixed bug — previously terminated silently).

## Worker Binaries

**`opencode` and `qwen` are installed system-wide.** `claude` and `gemini` are **not** present in this workspace.

- `adlai.toml` routes all nodes to `qwen/qwen3-coder-flash` (cheapest model for testing).
- Worker stdout is live-streamed at INFO level (`[worker:qwen]  │ <line>`). Stderr at WARNING (`[worker:qwen] ERR│ <line>`). Per-line truncated to 500 chars.
- Raw stdout per node saved to `.conductor/logs/<run_id>.stdout.log`.
- Prompts per node saved to `.conductor/logs/<run_id>.prompt.log`.
- Prompt size breakdown logged at INFO (agents_md / rvc / git / task / rej chars).
- `qwen` headless invocation: positional prompt + `-o stream-json`. `--approval-mode plan` for read-only. `-m <model>` passes model name.
- `opencode` headless invocation: `opencode run <prompt> -m <model>`. No `--approval-mode`.
- `create_worker(agentic, model=None, ...)` accepts `model` to pin specific LLM per node.
- Use `selftest` to dry-run graph compilation without invoking real workers.

## Pipeline Node Registry

The [[../20_Specs/PIPELINE_NODE_REGISTRY.md|PIPELINE_NODE_REGISTRY]] is the single source of truth mapping every defined conductor node to its pipeline position, routing key, and connection status. All node implementations should be verified against this registry.

## RVC Integration

When `--issue STORY-XX` is passed, the pipeline fetches the issue story and injects it into **plan** and **act** prompts.

- **Default (`--issue STORY-77`):** story-only via `rvc get STORY-77` (~2K chars).
- **`--extra-context`:** full vault dump via `rvc context STORY-77` (~80K chars, all linked docs/acceptance criteria/epics).
- **`--no-context`:** skip RVC entirely (fastest).
- The `rvc` binary is resolved from PATH, fallback to `~/.local/bin/rvc`.
- If the issue is not found or `rvc` fails, the pipeline logs a warning and continues (never breaks the run).
- RVC context is fetched fresh on every `plan` and `act` invocation so retries always have the latest vault state.

## Logging

- Console logging at INFO (DEBUG with `-v`) goes to stdout.
- Worker output live-printed at INFO/WARNING so the user sees progress in real-time.
- `.conductor/logs/<run_id>.log` — detailed file log, always DEBUG regardless of console level.
- `.conductor/logs/<run_id>.stdout.log` — raw stream-json output per node.
- `.conductor/logs/<run_id>.prompt.log` — full prompts sent to each node.
- `uv run conductor logs <run_id>` shows the ledger + tails last 8KB of the detailed log.
- `selftest` logs to `selftest-<project>.log`.

## Testing

- No unit tests in this repo.
- `uv run conductor selftest <project>` is the only built-in verification.
- `test_fixtures/` contains a fake repo and `qa-pass.sh` / `qa-fail.sh` for manual QA gate testing.

## Known Static Issues (do not re-introduce)

1. `qa_node` uses `subprocess.run(..., shell=True)` — unsafe if `qa_cmd` is ever user-controlled.
2. `plan_reviser_node` is a stub; it does not actually diagnose failures.
3. `WorkerResult.error` truncates stderr to last 2000 chars.
4. `_extract_stream_json` silently drops malformed lines.

## Config Notes

- Project TOML lives in `conductor/projects/<name>.toml`.
- `agents_md` path defaults to `<repo>/AGENTS.md` but can be overridden (ADLAI uses `~/Documents/ADLAI/CLAUDE.md`).
- `qa_cmd` is executed with `shell=True` in the `repo` directory.
- Routing fallback order: project TOML → `WORKER_CONFIG` dict → `DEFAULT_ROUTING` in `workers.py`.

## Next Steps

1. Test a real run: `conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77`
2. Compare with `--extra-context` to measure token savings (~80K vs ~2K).
3. Priority 4: replace `shell=True` with `shlex.split` in QA node (30–60 min).
4. Priority 5: wire up or drop unused `bulk` node (5 min).
5. Priority 6: add unit tests (2–3 days).
6. Priority 7: rebuild PlanReviser as a real diagnosis node (1–2 days).


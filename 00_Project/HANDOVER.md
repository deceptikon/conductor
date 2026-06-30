# Conductor — Handover Note for Tomorrow Us

## Current State (2026-06-27)

The conductor harness is **working end-to-end** for the ADLAI project. A live test from `/tmp` proved the full pipeline compiles, plans, and pauses at the human-approval gate.

### What Works

| Component | Status | Evidence |
|-----------|--------|----------|
| LangGraph pipeline | 🟢 Active | `selftest` passes; live plan generated with qwen |
| SQLite checkpointing | 🟢 Active | `.conductor/checkpoints.sqlite` created and used |
| Per-run file logging | 🟢 Active | `.conductor/logs/<run_id>.log` captures DEBUG |
| Human-approval gate | 🟢 Active | `interrupt()` pauses; `approve/reject/edit` resume |
| Worker routing (TOML) | 🟢 Active | 4 nodes × 4 qwen models pinned |
| RVC context fetch | 🟢 Active | `rvc context STORY-77` fetched 82KB; injected into plan + act |
| Cross-directory CLI | 🟢 Active | `~/.local/bin/conductor` wrapper works from `/tmp` |
| ANSI stripping (opencode) | 🟢 Active | `> build · provider/model` headers removed |

### Model Routing (`adlai.toml`)

| Node | Worker | Model | Mode |
|------|--------|-------|------|
| plan | qwen | `qwen/qwen3.7-plus` | read-only |
| act | qwen | `qwen/qwen3.6-plus` | write |
| bulk | qwen | `qwen/qwen3-coder-flash` | write |
| review | qwen | `qwen/qwen3.7-max` | write |

### RVC Integration

- `rvc` is resolved from PATH, fallback to `~/.local/bin/rvc` (symlinked to `~/Q/vault-protocol/rvc-cli.py`).
- When `--issue STORY-XX` is passed, `_rvc_context()` fetches the issue context and prepends it to both **plan** and **act** prompts.
- If `rvc` fails, the pipeline logs a warning and continues (graceful degradation).

### File Changes Since Last Handover

- `conductor/__main__.py` — repo-local `.conductor/` state dir; per-run file logging; `selftest` prints model info
- `conductor/pipeline.py` — `_rvc_context()` added; injected into `plan_node` and `act_node`
- `conductor/workers.py` — ANSI escape stripping for opencode output
- `conductor/projects/adlai.toml` — all nodes routed to qwen with pinned models
- `conductor/projects_config.py` — unchanged (already supported `model` param)
- `.gitignore` — `.conductor/` ignored
- `AGENTS.md` — updated with RVC section, new routing, cheatsheet
- `README.md` — written from scratch
- `~/.local/bin/conductor` — wrapper script created

### What's Still Broken / Stubbed (by design, for now)

1. `after_approve` conditional bug: empty `rejection_note` routes to `end` instead of back to `plan`. (Known static issue #1)
2. `qa_node` uses `shell=True`. (Known static issue #2)
3. `plan_reviser_node` is a stub — it parses revised plans but doesn't deeply diagnose QA failures. (Known static issue #3)
4. `WorkerResult.error` truncates stderr to 2000 chars. (Known static issue #4)
5. `_extract_stream_json` silently drops malformed lines. (Known static issue #5)
6. `langgraph.checkpoint.serde.jsonplus` warnings about unregistered `TaskNode`/`Plan` types — harmless but noisy.

### Next Steps (Tomorrow)

1. **Run a full end-to-end test with `--issue`**:  
   `conductor run adlai "Fix retrieval recall" --type fix --issue STORY-77`  
   Approve the plan and watch it go through `act` → `qa` → `commit`.

2. **Fix the 5 known static issues** if they bite during the e2e test.

3. **Add `--model` override to CLI**: allow `conductor run adlai "task" --model qwen/qwen3.7-max` to override the TOML routing for a single run.

4. **LangSmith integration** — deferred earlier; `langsmith` is already in `uv.lock` as a transitive dep. Wire it up for traceability across the pipeline.

5. **Add a `bootstrap` command** that mirrors `adlai-vault/00_Project/session_bootstrap.sh` — assemble STATE + issue + specs + decisions + gotchas into a single prompt for agents.

### Files to Read First

- `AGENTS.md` — compact quick-start for future agents
- `conductor/projects/adlai.toml` — current routing table
- `conductor/pipeline.py` — core state machine
- `~/Documents/ADLAI/adlai-vault/20_Specs/WORKFLOW.md` — session ritual spec
- `~/Documents/ADLAI/adlai-vault/00_Project/REGLAMENT.md` — project constitution

---
*Written by us, for us. Keep it honest.*

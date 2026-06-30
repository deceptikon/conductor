# Conductor — Recommendations

## Priority 1: RVC Context Bloat (trivial fix)

### Problem

`rvc context STORY-XX` recursively resolves every `[[wikilink]]` in the issue file
and dumps the **full raw content** of every linked document (specs, PRDs, epics,
acceptance criteria, related issues). For a typical story this produces **60–90K
chars** of context that gets injected wholesale into the prompt.

### Impact

- **Token waste**: the model pays attention to frontmatter, vault metadata, and
  unrelated content it doesn't need for the task.
- **Slow generation**: more tokens = more time + higher latency from the worker.
- **Context window pressure**: qwen3-coder-flash has a limited effective context
  window. Wasting 80K on vault dump leaves little room for reasoning.
- **Cost**: every node invocation pays for tokens it doesn't use.

### Solutions

| Option | Effort | Saving | Notes |
|--------|--------|--------|-------|
| `--rvc-mode off` | 1 hour | 100% | Skip vault entirely (best for testing) |
| `--rvc-mode get` | 1 hour | ~80% | Use `rvc get` instead of `rvc context` — single file only, no linked docs |
| `rvc get \| strip frontmatter` | 2 hours | ~85% | Pipe through sed to drop YAML frontmatter (`/^---$/,/^---$/d`), keep only the body |
| Add `--rvc-summary` to `rvc` | 4 hours | ~90% | Patch rvc-cli.py to support `--body-only` / strip frontmatter natively |
| Vault restructuring | days | variable | If stories routinely link to 20+ files, rethink how the vault organizes context |

**Recommended first step**: Add a `--rvc-mode` flag (`full` | `get` | `off`) to
`conductor run` so the user can choose. Default to `full` for backward compat,
switch to `get` for test runs.

---

## Priority 2: PlanReviser Is a Stub

### Problem

`plan_reviser_node` in `pipeline.py` (line 396) is documented as a stub. When
QA fails `max_qa_retries` times, it re-asks the planner to "diagnose" the
failure — but the prompt is generic and the result parsing is brittle:

```python
# Known issue #3: plan_reviser_node is a stub; it does not actually diagnose failures.
```

The reviser doesn't:
- Compare QA error output against each node's `test_case` to find which node is broken.
- Check whether the `expected_output` contract is satisfiable.
- Understand whether the failure is in the code or in the test.
- Split oversized nodes that regularly fail.

### Fix

Replace the stub with a real diagnosis loop:

1. Parse the QA log for test names, assertion failures, and stack traces.
2. Match failures to the node whose `test_case` or `expected_output` is implicated.
3. If a clear culprit node exists — revise just that node's contract and route back to `act`.
4. If the failure is systematic (e.g., bad architecture) — revise the whole `topo_order`.
5. If the plan is sound but execution keeps failing — escalate to human.

**Estimate**: 1–2 days of focused work.

---

## Priority 3: `after_approve` Known Bug

### Problem

Known issue #1 from `AGENTS.md`:

> empty `rejection_note` routes to `end` instead of back to `plan`.

When a human rejects with no note, the pipeline terminates instead of looping
back to the planner. This is incorrect — a rejection without a note should
still give the planner another chance (or at minimum, ask for a note).

### Fix

```python
def after_approve(state):
    if state.get("status") == "rejected":
        if state.get("rejection_note"):
            return "plan"         # re-plan with feedback
        # ── bug: empty note → "end" ──
        # Should be: return "plan" (without feedback)
        # or: ask human for a note, then route
```

**Estimate**: 15 minutes.

---

## Priority 4: `shell=True` in QA Node

### Problem

Known issue #2 from `AGENTS.md`:

> `qa_node` uses `subprocess.run(..., shell=True)` — unsafe if `qa_cmd` is ever user-controlled.

Currently `qa_cmd` is hardcoded in the project TOML, so the risk is low. But
if a future UI lets users set `qa_cmd` dynamically, this is a command-injection
vector.

### Fix

Switch to `shlex.split(cfg.qa_cmd)` + `shell=False`:

```python
proc = subprocess.run(
    shlex.split(cfg.qa_cmd), cwd=str(cfg.repo), shell=False,
    capture_output=True, text=True, timeout=1800,
)
```

This requires the TOML to use proper quoting for args (or split them as a list
in the config). A backwards-compat shim: try `shlex.split` first, fall back to
`shell=True`.

**Estimate**: 30–60 minutes.

---

## Priority 5: Bulk Node Is Wired but Unused

### Problem

`adlai.toml` defines `[routing.bulk]` pointing to `qwen-coder-flash`, but
no pipeline edge routes to a `"bulk"` node. The worker config exists purely
for the routing table.

### Options

- **Wire it up**: Add a `"bulk"` node to the graph for high-volume mechanical
  refactors (rename symbol across 50 files, update import paths, etc.). Route
  to it after the plan has been reviewed and approved, bypassing act/QA for
  trivial changes.
- **Drop it**: Remove `[routing.bulk]` from the TOML to avoid confusion.

**Estimate**: 1–2 hours to wire up, 5 minutes to drop.

---

## Priority 6: Prompt Debug Logging at Size

### Problem

Currently `logger.debug` at `-v` shows the full prompt as two chunks (first/
last 500 chars). For a 95K prompt this is adequate, but when debugging parse
failures or worker misbehaviour you need the **exact** prompt that was sent.

### Fix

Also save the prompt to `.conductor/logs/<run_id>.prompt.log` (one per run,
appending per node) so it's findable without `-v`:

```
=== plan ===
<full prompt text>
=== act ===
<full prompt text>
```

**Estimate**: 15 minutes (same pattern as `_save_raw_stdout`).

---

## Priority 7: AGENTS.md Referencing ADLAI

### Problem

The conductor's own `AGENTS.md` references the ADLAI project routing table,
Model pinning, and the ADLAI vault. This is useful context but makes the
AGENTS.md less reusable when onboarding a new project.

### Fix

Split the conductor's AGENTS.md into:
- `AGENTS.md` — generic conductor harness instructions (graph pipeline, CLI commands, state management).
- `projects/adlai.toml` — project-specific routing (already done).
- A separate doc for "how to add a new project" with a checklist.

**Estimate**: 1 hour.

---

## Priority 8: Unit Tests

### Problem

The test_fixtures/ directory contains a fake repo for manual QA gate testing,
but there are **no unit tests** for:
- `Plan.validate()` / `compute_topo_order()`
- `_extract_stream_json()`
- `_git_context()` / `_rvc_context()`
- Edge-case routing (empty rejection_note, zero nodes, cycles)
- Worker timeout / parse failure recovery

### Fix

Add pytest tests under `tests/`:
- `tests/test_schema.py` — Plan validation, DAG cycle detection, topo order.
- `tests/test_workers.py` — `_extract_stream_json` with valid/invalid/mixed input.
- `tests/test_pipeline.py` — conditional edge decisions (mock state).

**Estimate**: 2-3 days for a solid foundation.

---

## Summary

| # | Item | Effort | Impact |
|---|------|--------|--------|
| **1** | `--rvc-mode` flag | **1 hour** | **High** — saves 80% tokens on every call with `--issue` |
| **2** | PlanReviser stub | 1–2 days | High — but only matters when QA actually fails |
| **3** | `after_approve` empty-note bug | **15 min** | **Medium** — prevents silent termination on bare rejection |
| **4** | `shell=True` safety | 30–60 min | Low — not exploitable without dynamic qa_cmd |
| **5** | Bulk node unconnected | 5 min | Low — cosmetic |
| **6** | Save prompts to file | **15 min** | **Medium** — makes debugging much easier |
| **7** | Split AGENTS.md | 1 hour | Low — nice to have |
| **8** | Unit tests | 2-3 days | Medium — foundational but not urgent |

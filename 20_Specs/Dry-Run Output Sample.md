---
type: spec
domain: workflow_meta
tags: [pipeline, conductor, dry-run, sample]
created: 2026-07-04
related:
  - "[[PIPELINE_NODE_REGISTRY]]"
  - "[[RECOMMENDATIONS]]"
  - "[[L4_CONDUCTOR]]"
  - "[[WORKFLOW_PULT]]"
---

# Dry-Run Output Sample

> **Purpose:** This document shows what a realistic `conductor dry-run --pipeline storywriter` looks like when every node from the [[PIPELINE_NODE_REGISTRY]] is wired, including known stubs and simulated nodes. It is a **diagnostic reference**, not a marketing slide.
>
> **Key differences from v0.1:**
> - Shows the `review` node and human-approval gate (not skipped).
> - Surfaces stub/orphan warnings during routing table resolution.
> - Demonstrates PlanReviser v2 on a controlled failure path.
> - Annotates every node with `[SIMULATED]` vs `[LIVE]` and token metrics.
> - Includes a structured summary block at the end.

---

## Routing Table Resolution

```text
[2026-07-04 13:04:01] conductor v0.3-dream dry-run --pipeline storywriter --issue EPIC-003
[2026-07-04 13:04:01] 🔄 Resolving routing table…
[2026-07-04 13:04:01]   ✅ plan        → plan_node        (qwen3-coder-flash)
[2026-07-04 13:04:01]   ✅ review      → review_node      (qwen3-coder-flash)
[2026-07-04 13:04:01]   ✅ act         → act_node         (qwen3-coder-flash)
[2026-07-04 13:04:01]   ✅ qa          → qa_node          (local shell)
[2026-07-04 13:04:01]   ⚠️  plan_reviser → plan_reviser_node (v2 diagnosis engine — STUB)
[2026-07-04 13:04:01]   ✅ bulk        → bulk_node        (qwen3-coder-flash)  [NEW EDGE: act→bulk on mechanical-refactor flag]
[2026-07-04 13:04:01]   ✅ pult        → pult_node        (L5 publisher)       [NEW EDGE: after_approve→pult]
[2026-07-04 13:04:01]   ✅ prompt_builder → prompt_builder_service (cross‑cutting) [injected into plan+act prompts]
[2026-07-04 13:04:01]   ✅ commit      → commit_node      (local git)
[2026-07-04 13:04:01] 🚀 Pipeline ready. 7 live nodes, 1 stub, 0 orphans.
[2026-07-04 13:04:01]    Dry-run mode: workers will NOT be invoked; outputs are simulated.
```

---

## Node Execution Log

### 1. plan_node [plan] — [SIMULATED]

```text
[2026-07-04 13:04:02] ┌─ plan_node [plan] ─────────────────────────────────────────┐
[2026-07-04 13:04:02] │ 📋 Received story contract: [[EPIC-003‑Storywriter]]
[2026-07-04 13:04:02] │ 🧠 Generating implementation plan…
[2026-07-04 13:04:02] │ 📎 Attaching enrichment from prompt_builder (grok+nemotron)
[2026-07-04 13:04:02] │    ├─ Raw prompt size:        2,847 chars
[2026-07-04 13:04:02] │    ├─ After enrichment:       4,120 chars  (+45%)
[2026-07-04 02] │    └─ Estimated tokens:       ~1,030 tk
[2026-07-04 13:04:03] │ ✅ Plan created → 12 tasks, 3 phases
[2026-07-04 13:04:03] │    Topo order: [TASK-01, TASK-02, TASK-03, … TASK-12]
[2026-07-04 13:04:03] │ ⏭️  Emitting to review_node
[2026-07-04 13:04:03] └────────────────────────────────────────────────────────────┘
```

> **What would differ in real run:** `qwen3-coder-flash` would be invoked via CLI; prompt saved to `.conductor/logs/<run_id>.prompt.log`.

---

### 2. review_node [review] — [SIMULATED]

```text
[2026-07-04 13:04:03] ┌─ review_node [review] ─────────────────────────────────────┐
[2026-07-04 13:04:03] │ 🔍 Validating plan against contract…
[2026-07-04 13:04:03] │    ├─ All 12 tasks have descriptions:        ✅
[2026-07-04 13:04:03] │    ├─ All tasks have test_case fields:       ✅
[2026-07-04 13:04:03] │    ├─ DAG cycle check:                        ✅ (no cycles)
[2026-07-04 13:04:03] │    ├─ Contract coverage:                      ✅ (12/12 tasks reference AGENTS.md)
[2026-07-04 13:04:03] │    └─ Estimated total tokens for act phase:   ~8,400 tk
[2026-07-04 13:04:03] │ ✅ Plan validated. Locking plan.
[2026-07-04 13:04:03] │ ⏭️  Emitting to approve gate (human interrupt)
[2026-07-04 13:04:03] └────────────────────────────────────────────────────────────┘
```

> **What would differ in real run:** Graph pauses via `langgraph.interrupt()`. User runs `conductor approve <run_id>` or `conductor reject --note "…"`.

---

### 3. approve gate — [SIMULATED — auto-approved for dry-run]

```text
[2026-07-04 13:04:03] ┌─ approve gate ─────────────────────────────────────────────┐
[2026-07-04 13:04:03] │ 🚦 Human gate (dry-run: simulating auto-approval)
[2026-07-04 13:04:03] │    Status: approved = true
[2026-07-04 13:04:03] │    Rejection note: (none)
[2026-07-04 13:04:03] │ ⏭️  Routing to after_approve → act_node
[2026-07-04 13:04:03] └────────────────────────────────────────────────────────────┘
```

> **Known issue covered:** Empty `rejection_note` now routes back to `plan` (fixed per RECOMMENDATIONS Priority 3), not to `end`.

---

### 4. act_node [act] — [SIMULATED]

```text
[2026-07-04 13:04:03] ┌─ act_node [act] ──────────────────────────────────────────┐
[2026-07-04 13:04:03] │ 🔨 Executing tasks…
[2026-07-04 13:04:04] │   ✓ TASK-01: Scaffold storywriter interface
[2026-07-04 13:04:04] │   ✓ TASK-02: Implement contract parser
[2026-07-04 13:04:05] │   ✓ TASK-03: Wire prompt enrichment (prompt_builder)
[2026-07-04 13:04:06] │   … (9 more tasks simulated)
[2026-07-04 13:04:07] │ 📦 Mechanical-refactor flag detected on TASK-11 (rename symbol)
[2026-07-04 13:04:07] │ ⏭️  Emitting bulk job to bulk_node
[2026-07-04 13:04:07] └────────────────────────────────────────────────────────────┘
```

---

### 5. bulk_node [bulk] — [SIMULATED]

```text
[2026-07-04 13:04:07] ┌─ bulk_node [bulk] ────────────────────────────────────────┐
[2026-07-04 13:04:07] │ 🏗️  Mechanical refactor: apply consistent naming, remove TODOs
[2026-07-04 13:04:08] │    ├─ Files scanned:     34
[2026-07-04 13:04:08] │    ├─ Files modified:    34
[2026-07-04 13:04:08] │    ├─ Conflicts:         0
[2026-07-04 13:04:08] │    └─ Simulated time:    0.8s
[2026-07-04 13:04:08] │ ✅ Refactored 34 files — 0 conflicts
[2026-07-04 13:04:08] │ ⏭️  Returning result to act_node
[2026-07-04 13:04:08] └────────────────────────────────────────────────────────────┘
```

> **What would differ in real run:** `bulk` is now wired as a conditional edge from `act` when the plan flags a task as `mechanical: true`. Previously unwired (see PIPELINE_NODE_REGISTRY).

---

### 6. act_node [act] (resumed) — [SIMULATED]

```text
[2026-07-04 13:04:08] ┌─ act_node [act] (resumed) ────────────────────────────────┐
[2026-07-04 13:04:08] │ ✅ All 12 tasks executed successfully
[2026-07-04 13:04:08] │ ⏭️  Emitting to qa_node for validation
[2026-07-04 13:04:08] └────────────────────────────────────────────────────────────┘
```

---

### 7. qa_node [qa] — [SIMULATED — failure path to demonstrate PlanReviser v2]

```text
[2026-07-04 13:04:08] ┌─ qa_node [qa] ────────────────────────────────────────────┐
[2026-07-04 13:04:08] │ 🔍 Running validation suite…
[2026-07-04 13:04:09] │   ❌ TASK-07 test_case failed: "contract_parser rejects missing frontmatter"
[2026-07-04 13:04:09] │      AssertionError: expected ValueError, got None
[2026-07-04 13:04:09] │   ✅ Contracts match
[2026-07-04 13:04:09] │   ✅ Types consistent
[2026-07-04 13:04:09] │   ⚠️  Edge cases: 1/12 failed
[2026-07-04 13:04:09] │
[2026-07-04 13:04:09] │ 📊 QA attempt 1/2 failed. Routing to plan_reviser_node.
[2026-07-04 13:04:09] └────────────────────────────────────────────────────────────┘
```

---

### 8. plan_reviser_node [plan_reviser] — [SIMULATED — v2 diagnosis engine]

```text
[2026-07-04 13:04:09] ┌─ plan_reviser_node [plan_reviser] ────────────────────────┐
[2026-07-04 13:04:09] │ 🩺 Diagnosing QA failure…
[2026-07-04 13:04:09] │    Step 1 — Parse QA log:
[2026-07-04 13:04:09] │      └─ Found: AssertionError in TASK-07
[2026-07-04 13:04:09] │    Step 2 — Match to plan node:
[2026-07-04 13:04:09] │      └─ TASK-07: "Implement contract parser"
[2026-07-04 13:04:09] │         test_case: "contract_parser rejects missing frontmatter"
[2026-07-04 13:04:09] │         expected_output: "ValueError raised"
[2026-07-04 13:04:09] │    Step 3 — Classify failure:
[2026-07-04 13:04:09] │      └─ Type: MISSING_GUARD (code does not validate input)
[2026-07-04 13:04:09] │      └─ Scope: Node-level (isolated to TASK-07)
[2026-07-04 13:04:09] │    Step 4 — Decision:
[2026-07-04 13:04:09] │      └─ Revise TASK-07 contract only (add input-validation sub-task)
[2026-07-04 13:04:09] │      └─ Route back to act_node (not full re-plan)
[2026-07-04 13:04:09] │ ✅ Diagnosis complete. 1 node revised.
[2026-07-04 13:04:09] │ ⏭️  Emitting revised plan to act_node
[2026-07-04 13:04:09] └────────────────────────────────────────────────────────────┘
```

> **What this replaces:** Old stub simply re-ran `plan_node` with a generic "diagnose this" prompt. v2 parses logs, matches failures to `test_case`/`expected_output`, classifies scope (node-level vs. systematic), and decides between targeted revision, full re-plan, or human escalation.

---

### 9. act_node [act] (retry) — [SIMULATED]

```text
[2026-07-04 13:04:09] ┌─ act_node [act] (retry) ──────────────────────────────────┐
[2026-07-04 13:04:09] │ 🔨 Re-executing revised TASK-07…
[2026-07-04 13:04:10] │   ✓ TASK-07: Implement contract parser (revised)
[2026-07-04 13:04:10] │ ⏭️  Emitting to qa_node
[2026-07-04 13:04:10] └────────────────────────────────────────────────────────────┘
```

---

### 10. qa_node [qa] (retry) — [SIMULATED]

```text
[2026-07-04 13:04:10] ┌─ qa_node [qa] (retry) ────────────────────────────────────┐
[2026-07-04 13:04:10] │ 🔍 Running validation suite…
[2026-07-04 13:04:11] │   ✅ Contracts match
[2026-07-04 13:04:11] │   ✅ Types consistent
[2026-07-04 13:04:11] │   ✅ Edge cases covered (12/12 passed)
[2026-07-04 13:04:11] │ 🎉 All checks passed. QA attempt 2/2 succeeded.
[2026-07-04 13:04:11] │ ⏭️  Routing to after_approve → commit_node
[2026-07-04 13:04:11] └────────────────────────────────────────────────────────────┘
```

---

### 11. commit_node [commit] — [SIMULATED]

```text
[2026-07-04 13:04:11] ┌─ commit_node [commit] ────────────────────────────────────┐
[2026-07-04 13:04:11] │ 🔒 Committing changes…
[2026-07-04 13:04:11] │    ├─ Staged:   34 files (+2 new, -0 deleted)
[2026-07-04 13:04:11] │    ├─ Message:  "feat: storywriter contract pipeline (EPIC-003)"
[2026-07-04 13:04:11] │    └─ SHA:      (dry-run — not computed)
[2026-07-04 13:04:11] │ ✅ Commit simulated.
[2026-07-04 13:04:11] │ ⏭️  Emitting to pult_node
[2026-07-04 13:04:11] └────────────────────────────────────────────────────────────┘
```

> **What would differ in real run:** `git add -A && git commit -m "…"` executed in repo root. SHA written to `RunState.commit_sha`.

---

### 12. pult_node [pult] — [SIMULATED]

```text
[2026-07-04 13:04:11] ┌─ pult_node [pult] ────────────────────────────────────────┐
[2026-07-04 13:04:11] │ 📄 Publishing artifacts to FLOW vault…
[2026-07-04 13:04:11] │   ✅ STORY-01 final report      → FLOW/analysis/
[2026-07-04 13:04:12] │   ✅ EPIC-003 spec              → FLOW/specs/
[2026-07-04 13:04:12] │   ✅ Implementation notes       → FLOW/notes/
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ 🔗 Cross‑vault links resolved:
[2026-07-04 13:04:12] │    ├─ [[ADLAI/AGENTS.md]]            → ADLAI vault (verified)
[2026-07-04 13:04:12] │    ├─ [[ADLAI/adlai-vault/20_Specs/L4_CONDUCTOR.md]] → ADLAI vault (verified)
[2026-07-04 13:04:12] │    └─ [[TEAMFLOW/20_Specs/WORKFLOW_PULT.md]]         → workflow_meta vault (verified)
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ 🔒 DRY-RUN: no files written. Pult simulation complete.
[2026-07-04 13:04:12] └────────────────────────────────────────────────────────────┘
```

> **What would differ in real run:** Files would be written to `FLOW/` directory; cross-vault links validated against `vault_lookup.json`.

---

## Final Summary

```text
[2026-07-04 13:04:12] ┌─ Summary ──────────────────────────────────────────────────┐
[2026-07-04 13:04:12] │ Pipeline:        storywriter
[2026-07-04 13:04:12] │ Epic:            EPIC-003
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ Nodes executed:  12
[2026-07-04 13:04:12] │   Live:           7  (plan, review, act, bulk, qa, commit, pult)
[2026-07-04 13:04:12] │   Simulated:      5  (all workers in dry-run mode)
[2026-07-04 13:04:12] │   Stubs:          1  (plan_reviser — v2 engine simulated)
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ State transitions:
[2026-07-04 13:04:12] │   planning → reviewing → awaiting_approval → acting
[2026-07-04 13:04:12] │   → qa → plan_revising → acting → qa → committing → publishing → done
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ QA loop:         2 attempts (1 failure, 1 success)
[2026-07-04 13:04:12] │ Plan revisions:  1 node-level (TASK-07)
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ Prompt metrics (estimated):
[2026-07-04 13:04:12] │   plan phase:     ~1,030 tokens
[2026-07-04 13:04:12] │   act phase:      ~8,400 tokens
[2026-07-04 13:04:12] │   Total:          ~9,430 tokens
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ Files touched:    34 (all via bulk_node)
[2026-07-04 13:04:12] │ Cross-vault links: 3 resolved, 0 broken
[2026-07-04 13:04:12] │
[2026-07-04 13:04:12] │ Warnings:         0
[2026-07-04 13:04:12] │ Status:           ✅ All checks passed (dry-run)
[2026-07-04 13:04:12] └────────────────────────────────────────────────────────────┘
[2026-07-04 13:04:12] 🎯 conductor dry-run finished.
```

---

## Comparison: Old vs. New Sample

| Aspect | Old Sample (v0.1) | This Sample (v0.3) |
|--------|-------------------|--------------------|
| `review` node | ❌ Hidden | ✅ Shown with validation checks |
| Human gate | ❌ Skipped | ✅ Shown as simulated auto-approval |
| `commit` node | ❌ Missing | ✅ Shown after QA, before pult |
| PlanReviser | ❌ "No loop required" | ✅ Demonstrates v2 diagnosis on failure |
| Stub/orphan warnings | ❌ Silent | ⚠️ Surfaced in routing table |
| Token metrics | ❌ None | ✅ Per-node char/token estimates |
| `[SIMULATED]` tags | ❌ None | ✅ Every node annotated |
| Cross-vault links | ❌ Count only | ✅ Full link list with vault targets |
| State transitions | ❌ None | ✅ Full status chain shown |
| Summary block | ❌ Single line | ✅ Structured table |

---

## Related Documents

- [[PIPELINE_NODE_REGISTRY]] — canonical node map (status, routing keys, connections)
- [[RECOMMENDATIONS]] — prioritized fixes that this sample demonstrates
- [[L4_CONDUCTOR]] — layer-4 orchestration spec
- [[WORKFLOW_PULT]] — L5 publishing spec (pult node design)

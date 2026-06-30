---
type: task
status: Backlog
priority: P1
started: 2026-06-15
id: STORY-87
tags: "[cicd, citation, database, frontend, infra, llm, observability, review-queue, testing]"
---

# STORY-87: Workflow Layered Architecture — OSI-Style Enforcement Model

> **Meta-Project Integration Note:** This is **not** a core ADLAI feature. This story
> tracks the evolution and integration of the **Workflow Engine** (a sibling/meta-project)
> into the ADLAI codebase.
>
> - **Meta-Project (The Factory):** `~/Q/conductor` + `~/Q/vault-protocol`
> - **Target Project (The Product):** `~/Documents/ADLAI`
> - **Integration Point:** `adlai-vault/00_Project/session_bootstrap.sh` & `WORKFLOW.md`

---

## The Core Problem

A flat markdown document (WORKFLOW.md) with 19 numbered steps across 4 phases.
The LLM reads it and can freely ignore any step. It's a **suggestion**, not a **protocol**.

Test proof: Big Pickle read the workflow, announced "following the ritual," then
immediately went off-piste to investigate OpenCode internals instead of
SYNC → announce → ENGAGE → ACT.

**Root cause:** There is nothing enforcing the sequence. The workflow has no teeth.

---

## The OSI-Style Model

Each layer constrains the layer below it. Protocols between layers are explicit.
A layer cannot be skipped — the lower layer never receives the data to skip it.

```
┌──────────────────────────────────────────────────┐
│ LAYER 5 — Bootstrap                               │
│   session_bootstrap.sh                            │
│   "Assemble everything the agent needs. Deliver   │
│    once."                                         │
│   Protocol: context payload → Layer 4             │
│   STATUS: ✅ BUILT (v2, safe heredoc, lean)       │
├──────────────────────────────────────────────────┤
│ LAYER 4 — Conductor (outer enforcement ring)      │
│   Plan → Approve → Act → QA → Commit              │
│   Hard LangGraph nodes, checkpointed, human       │
│   interrupt at Approve. Stateless workers.        │
│   Protocol: node_name + state → Layer 3           │
│   STATUS: ✅ BUILT (~/Q/conductor)                 │
├──────────────────────────────────────────────────┤
│ LAYER 3 — Phase Gating (inner enforcement ring)   │
│   SYNC → ENGAGE → ACT → WRAP                      │
│   Each phase = one prompt. One LLM invocation.    │
│   Phase N's output is Phase N+1's input. The LLM  │
│   cannot skip phases because it never sees them.  │
│   Protocol: phase + required_artifact → Layer 2   │
│   STATUS: ❌ MISSING — this is the critical gap    │
├──────────────────────────────────────────────────┤
│ LAYER 2 — Artifacts (handoff protocol)            │
│   STATE.json, DECISIONS.md, GOTCHAS.md            │
│   "What happened, what was decided, what to       │
│    avoid." Cross-session state is always here.    │
│   Protocol: read state → act → write state        │
│   STATUS: ✅ BUILT (initialized, working)          │
├──────────────────────────────────────────────────┤
│ LAYER 1 — Tool Sandbox                            │
│   Permissions: read-only in SYNC, write in ACT,   │
│   no destructive ops ever.                        │
│   Protocol: phase → allowed_actions               │
│   STATUS: ⚠️ PARTIAL (Hermes has perms, not       │
│           phase-aware)                            │
├──────────────────────────────────────────────────┤
│ LAYER 0 — Model (substrate)                       │
│   The LLM itself. No control, only steering.      │
│   STATUS: ⚠️ PARTIAL (big-pickle works, local     │
│           Ollama broken for headless)             │
└──────────────────────────────────────────────────┘
```

---

## Interlayer Protocols

| From → To | What flows | How |
|---|---|---|
| L5 → L4 | Context payload | Bootstrap script output → conductor worker prompt |
| L4 → L3 | Pipeline node + state | Conductor feeds phase-specific prompt to agent |
| L3 → L2 | Phase completion artifact | SYNC produces announcement, ENGAGE updates state, ACT produces code, WRAP produces commit |
| L2 → L1 | Current phase | Phase name determines tool permissions |
| L1 → L0 | Available tool set | Model receives filtered tool list |

---

## The Missing Layer: L3 Phase Gating

**What it must do:**

A single issue run becomes 4 separate LLM invocations. Each invocation gets a
prompt that describes ONLY its phase. The prompt ends with a hard boundary:
"STOP here. Do not proceed."

```
INVOCATION 1 (SYNC):
  Prompt: "Read STATE.json, the issue, linked specs, decisions, gotchas.
           Announce what you found. Do NOT write code. Do NOT transition.
           Output a SYNC_ANNOUNCEMENT.md artifact."
  → Output: SYNC_ANNOUNCEMENT.md exists

INVOCATION 2 (ENGAGE):
  Prompt: "Read the SYNC announcement. Transition the issue. Update STATE.json.
           Read relevant specs for the code you'll change. Do NOT write code yet.
           Output an ENGAGE_PLAN.md artifact."
  → Output: ENGAGE_PLAN.md exists

INVOCATION 3 (ACT):
  Prompt: "Read the engage plan. Implement. Update specs if code changed.
           Run tests. Fix failures (max 3 attempts). Do NOT commit until QA passes."
  → Output: tests pass (exit code 0)

INVOCATION 4 (WRAP):
  Prompt: "Commit. Transition issue to Review. Append to DECISIONS.md and
           GOTCHAS.md. Update STATE.json to clear. Announce result."
  → Output: commit SHA + clean STATE.json
```

**Two approaches:**

### Approach A — Dirty-Quick (shell script)

`session_bootstrap.sh` gains a `--phase <N>` flag. Each phase outputs a
self-contained prompt ending with a STOP boundary. The conductor chains them
as separate `opencode run` calls, feeding the prior phase's output as context.

```bash
# Example: running all 4 phases
opencode run --model "opencode/big-pickle" --pure \
  "$(bash session_bootstrap.sh --phase sync STORY-87)" | tee sync_out.md
opencode run --model "opencode/big-pickle" --pure \
  "$(bash session_bootstrap.sh --phase engage STORY-87) --prev-output sync_out.md"
# ... etc
```

**Pro:** Shell script, testable immediately, no conductor changes needed.
**Con:** Manual chaining, human has to run 4 commands. Phase artifacts are loose files.

### Approach B — Proper (conductor sub-graph)

The conductor's `ActNode` becomes a sub-graph:
`SyncNode → EngageNode → ActNode → WrapNode`.
Each node calls the bootstrap with `--phase <N>` internally.
Checkpointed between nodes.

**Pro:** Fully automated, checkpointed, resilient to failures.
**Con:** Requires conductor code changes. More complex to debug.

**Recommendation:** Start with Approach A to validate the concept.
Prove that 4-phase gating produces better compliance than 1-phase flat-doc.
Then promote to Approach B inside conductor.

---

## Bottlenecks Mapped to Layers

| Bottleneck | Layer | Status |
|---|---|---|
| Context bloat (74KB+) | L5 | ✅ Fixed — lean prompt, WORKFLOW.md not dumped |
| Bash heredoc unsafe | L5 | ✅ Fixed — temp file + safe heredoc |
| **Model ignores workflow** | **L3** | **❌ Missing — this story** |
| Ollama provider broken | L0 | ⚠️ Workaround: big-pickle |
| Shallow git context | L5 | ⚠️ Low priority |

---

## Action Plan

1. **Add `--phase` flag to `session_bootstrap.sh`**
   - `--phase sync` outputs only SYNC prompt ending with STOP
   - `--phase engage` outputs ENGAGE prompt (reads prev phase output)
   - `--phase act` outputs ACT prompt
   - `--phase wrap` outputs WRAP prompt
   - Default (no flag): current behavior (all-in-one, for humans)

2. **Test manually** — run all 4 phases sequentially on STORY-87, verify each
   phase produces the right artifact before proceeding

3. **Define artifact gates** — a helper script `check_phase.sh <phase>` that
   verifies the required artifact exists before allowing the next phase

4. **Conductor integration** — once manual testing proves compliance,
   wire the `--phase` flow into `~/Q/conductor`'s ActNode as a sub-graph

---

## Definition of Done

- [ ] `session_bootstrap.sh --phase sync STORY-NN` outputs a prompt that
  ends with a hard STOP boundary and only permits read operations
- [ ] `--phase engage`, `--phase act`, `--phase wrap` all work
- [ ] Manual 4-phase run on STORY-87 completes with proper artifacts at each gate
- [ ] Each phase's output feeds correctly into the next phase's context
- [ ] agent follows the flow (no off-piste navigation) in at least 2 test runs
- [ ] (Optional) Conductor ActNode sub-graph wired to `--phase` flag

---

## RVC Dependency & Pre-flight Check

### Problem

`session_bootstrap.sh:62-65` calls `rvc issue` and `rvc context`
unconditionally. If `rvc` is not in PATH, the commands silently fail via
`|| echo` fallback, producing `"(issue not found)"` and `"(no linked specs)"`
in the prompt. The user gets no indication that the prompt is degraded.

This is a **soft dependency** — the script works without rvc, but the
prompt quality is lower (missing issue title, description, linked specs).

### Solution: Pre-flight health check

A non-fatal pre-flight check was added at line 39:

```bash
if ! command -v rvc &>/dev/null; then
  echo "WARN: rvc CLI not found in PATH — issue content and linked specs will be placeholder text." >&2
fi
```

This warns on stderr without changing behavior. The existing `rvc issue` /
`rvc context` calls (with `|| echo` fallback) remain unchanged — no
degradation.

### Test coverage (4 tests)

| Test | What it verifies |
|------|-----------------|
| `test_sync_fallback_text_without_rvc` | Without rvc, issue content shows `"(issue not found)"` fallback |
| `test_sync_structure_preserved_without_rvc` | Prompt structure (ARTIFACT TARGET, HARD STOP, phase header) intact without rvc |
| `test_legacy_fallback_text_without_rvc` | Legacy mode also uses fallback text without rvc |
| `test_warning_emitted_when_rvc_missing` | Stderr warning mentions rvc when PATH excludes it |

Tests run in `TestRvcAbsentBehavior` in `test_session_bootstrap.py`.

### Design decisions

1. **No mocking** — Tests strip rvc from PATH, don't inject a mock binary.
   This verifies the actual fallback path, not a simulated one.
2. **Non-fatal** — Missing rvc is a warning, not an error. The script
   continues and produces a degraded-but-usable prompt.
3. **No change to rvc calls** — The `rvc issue` / `rvc context` lines
   (62, 65) are untouched. Only a pre-flight check was added.
4. **Stderr for warnings** — Warnings go to stderr, never to stdout
   (which carries the prompt).

### Future

If rvc becomes a hard dependency, the pre-flight check can be promoted to
an error exit. For now, the soft-fallback is more robust for CI and
development environments.

---

## L3 Artifacts

### SYNC

<!-- l3:phase=sync story=STORY-87 status=pending version=1 -->

Timestamp: 2026-06-15T22:28:00Z
Git branch: prompts
Git head: b7eaaa8
Dirty files: 2

Context Summary:
*(review context above and summarize)*

Readiness: *(write "ready" or "blocked" with reason)*

Missing:
*(list any blockers or write "none")*

Boundary:
- No implementation was performed during SYNC.
- No tests were run during SYNC.
- No commit was made during SYNC.

<!-- /l3:phase=sync -->

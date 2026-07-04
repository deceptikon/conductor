---
domain: workflow_meta
domain_tags: []

# ADLAI Flow Analysis: Integration of Conductor + RVC into a Legal AI Product

*Generated: 2026-06-28*
*Analyst: OpenCode*
*Scope: Deep-dive into how the agent orchestration stack (Conductor + RVC) integrates with the ADLAI legal AI product*

---

## 1. What is ADLAI?

ADLAI is an AI-native Saudi legal assistant (bilingual AR/EN hybrid-RAG) with the following components:

- **Backend:** Python FastAPI + Postgres + pgvector
- **Frontend:** Vue 3 SPA
- **RAG Pipeline:** Hybrid retrieval (BM25 + dense), citation verification, reasoning router
- **Review Queue:** Attorney-facing UI for uncertain responses
- **Corpus:** Saudi regulations (ZATCA, SAMA, PDPL, MISA, etc.)

But ADLAI is also something else: **the first battle-tested consumer of the Conductor+RVC stack.** Every story, epic, spec, and decision in `adlai-vault/` is managed by RVC and processed through Conductor. The product and the orchestration stack co-evolved.

---

## 2. The Flow Architecture in Practice

### 2.1 Layer 5 — Bootstrap (`session_bootstrap.sh`)

**Current implementation:** A 436-line bash script that assembles context and emits prompts.

**What it reads:**
1. `STATE.json` — current active issue/branch/agent
2. `DECISIONS.md` — last 3 decisions (strip boilerplate via awk)
3. `GOTCHAS.md` — last 3 gotchas
4. Issue content via `rvc issue <ID>`
5. Linked specs via `rvc context <ID>`
6. Git state (branch, status, log)

**What it emits:** A self-contained prompt string piped into `opencode run` or `qwen`.

**Critical bug (from STORY-87):** `$STORY_FILE` is only set for `sync|engage` phases. ACT and WRAP phases always fail immediately because the story file path is never resolved.

```bash
# session_bootstrap.sh:126-128 — THE BUG
if [[ -n "$PHASE" && ("$PHASE" == "sync" || "$PHASE" == "engage") ]]; then
  STORY_FILE=$(find "$VAULT/10_Issues" -name "${ISSUE_ID}-*.md" -type f 2>/dev/null | head -1 || true)
fi
```

### 2.2 Layer 4 — Conductor

**Current integration:** The conductor runs ADLAI tasks via `adlai.toml`:

```toml
[routing.plan]
worker = "qwen"
model = "qwen/qwen3-coder-flash"
read_only = true

[routing.act]
worker = "qwen"
model = "qwen/qwen3-coder-flash"
```

**QA gate:** `uv run pytest backend/tests/unit -q`

**RVC integration:** `--issue STORY-XX` fetches context via `rvc get` (default) or `rvc context` (`--extra-context`).

**Gap:** Conductor's `ActNode` treats the plan as a monolith. It does NOT currently call `session_bootstrap.sh --phase sync/engage/act/wrap`. The L3 phase gating is entirely outside Conductor's graph. This is by design (EPIC-15 non-goals state "No changes to L4 Conductor core logic"), but it means the two systems are not yet integrated.

### 2.3 Layer 3 — Phase Gating

**The heart of the problem.** A single Conductor Act invocation becomes 4 separate LLM invocations:

```
INVOCATION 1 (SYNC):     Read state/issue/specs → announce → write SYNC artifact
INVOCATION 2 (ENGAGE):   Read SYNC artifact → transition issue → plan → write ENGAGE artifact
INVOCATION 3 (ACT):      Read ENGAGE plan → implement → test → write ACT artifact
INVOCATION 4 (WRAP):     Read ACT results → commit → transition → log decisions/gotchas
```

**Each prompt ends with a hard STOP.** The LLM cannot skip phases because it never sees them.

**Current status:**
- SYNC: ✅ Built, tested, auto-generates artifact
- ENGAGE: ✅ Built, gates on SYNC ready
- ACT: 🔴 Broken (`$STORY_FILE` not set)
- WRAP: 🔴 Broken (`$STORY_FILE` not set)

### 2.4 Layer 2 — Artifacts

**Cross-session state lives in the vault:**

| File | Purpose | Written by |
|------|---------|------------|
| `STATE.json` | Current active issue, branch, agent, timestamps | ENGAGE agent |
| `DECISIONS.md` | Architectural decisions with rationale | WRAP agent |
| `GOTCHAS.md` | Non-obvious findings to avoid | WRAP agent |
| `REGLAMENT.md` | Living status ledger | Human + rescan |
| Story file `## L3 Artifacts` | Phase completion proofs | Agent per phase |

### 2.5 Layer 1 — Tool Sandbox

**Permissions per phase (designed, not fully enforced):**

| Phase | Allowed Tools | Forbidden |
|-------|---------------|-----------|
| SYNC | read_file, search_files, rvc_* (read) | write_file, edit, git commit, rvc issue start |
| ENGAGE | rvc_issue_start, write_file (STATE only) | edit source code, run tests |
| ACT | write_file, edit, run_shell_command | git commit, rvc issue review |
| WRAP | git, rvc_issue_review, write_file (DECISIONS/GOTCHAS) | edit source code, run tests |

**Current enforcement:** Prompt instructions only. No actual tool filtering happens at the LLM client level. This is a known gap.

---

## 3. ADLAI-Specific Findings from Vault Audit

### 3.1 Story Distribution

| Status | Count | Notes |
|--------|-------|-------|
| Done | ~35 | Including EPIC-01 through EPIC-07 |
| Review | ~20 | Including STORY-77 (retrieval ground truth), STORY-83 (ZATCA) |
| Active | 1 | STORY-87 (workflow architecture) |
| To Do | ~10 | Including EPIC-15 and all pult stories |
| Backlog | ~5 | Including deployment stories |

### 3.2 The "Pult" Naming Convention

"Pult" (пульт) is Russian for "remote control" or "control panel." It was chosen deliberately:
- **Factory metaphor:** Conductor+RVC is "The Factory" (meta-project)
- **Product metaphor:** ADLAI is "The Product"
- **Pult** is the control panel that operates the factory to build the product

This naming convention appears in:
- `WORKFLOW_PULT.md`
- `EPIC-15` ("Workflow Orchestration & Pult Integration")
- All STORY-95 through STORY-99

### 3.3 Test Reality Gap

**103 tests pass, but they test fiction:**

```
test_bootstrap_cli.py        (10) — flags, env vars, exit codes
test_phase_sync.py           (13) — SYNC artifact, prompt content
test_phase_engage.py         (4)  — ENGAGE gating
test_phase_act.py            (4)  — ACT gating (pytest, no-commit)
test_phase_wrap.py           (4)  — WRAP gating
test_gate_errors.py          (9)  — L3 error cases
test_artifact_schema.py      (7)  — L2 field validation
test_full_pipeline.py        (1)  — golden path (mocked)
test_idempotence.py          (6)  — re-run safety
test_sandbox_lifecycle.py    (6, ALL SKIPPED) — L1 worktrack
```

**The problem:** Every test uses `temp_vault` fixtures with synthetic story files. No test validates that `rvc context STORY-87` on the **real** ADLAI vault returns real specs, real decisions, real gotchas. The prompt could be 80% placeholder text and all tests would still pass.

**STORY-98** addresses this: 2 E2E tests against the real vault, asserting the full lifecycle.

### 3.4 The Prompt Bloat Problem

**Concrete measurement from STORY-87:**

```
Legacy mode (all 4 phases in one prompt): 2080 lines
Sync mode (SYNC only):                    662 lines
HARD STOP position in SYNC:               line 649
Context before HARD STOP:                 ~385 lines
```

The 385 lines of context (issue + specs + decisions + gotchas + git state) appear **before** the instruction "Do NOT write code." By line 385, the model has already processed the entire implementation problem and begun planning.

**Fix (STORY-97):** Move phase instruction + HARD STOP to the **first 5 lines** of output. Context follows the instruction.

### 3.5 The Silent Failure Problem

**Current behavior when `rvc` is missing:**

```bash
# session_bootstrap.sh:39-42
if ! command -v rvc &>/dev/null; then
  echo "WARN: rvc CLI not found..." >&2
fi
# Script continues with placeholder text
```

The warning goes to stderr. If the caller pipes stdout to `opencode run`, the warning is lost. The LLM receives a prompt with `"(issue not found)"` and `"(no linked specs)"` but has no way to know the data is degraded.

**Fix (STORY-95):** `ErrorClassifier` captures stderr, classifies it (`MISSING_CLI`, `INVALID_PATH`, etc.), writes structured JSON logs to vault, and raises `PultError` with the structured payload.

---

## 4. Integration Pain Points

### 4.1 Conductor ↔ ADLAI Flow Gap

**Current state:** Conductor runs ADLAI tasks as a single Act invocation. The agent receives the full AGENTS.md contract + locked plan + RVC context and is expected to implement everything in one shot.

**What ADLAI flow wants:** Conductor's Act node should become a sub-graph:

```
ActNode:
  SyncSubNode   → runs --phase sync,   produces SYNC artifact
  EngageSubNode → runs --phase engage, produces ENGAGE artifact
  ActSubNode    → runs --phase act,    produces code + ACT artifact
  WrapSubNode   → runs --phase wrap,   produces commit + WRAP artifact
```

Each sub-node is checkpointed. If ACT fails QA, it loops back to ActSubNode (not the whole plan). If WRAP fails, the human can inspect the ACT artifact and retry.

**Status:** Not implemented. STORY-87 mentions it as "Optional Phase 3."

### 4.2 RVC ↔ ADLAI Flow Gap

**Current state:** `rvc context STORY-XX` recursively resolves wikilinks and dumps full linked specs. For ADLAI stories that link to 10+ specs, this produces 60–90K chars.

**What ADLAI flow wants:** Phase-specific context. SYNC needs the issue + high-level specs. ENGAGE needs the issue + relevant specs for the planned change. ACT needs the ENGAGE plan + target files. WRAP needs the diff + test results.

**The pult solution (Phase 4 in WORKFLOW_PULT.md):** Lazy/dynamic loading. Instead of dumping everything, `pult` assembles phase-specific payloads. If an issue tags `domain: database`, only `DB-Schema.md` is injected.

### 4.3 Path Resolution Chaos

**Three different path strategies in one codebase:**

```bash
# session_bootstrap.sh
VAULT="${VAULT:-/home/lexx/Documents/ADLAI/adlai-vault}"

# Some Python script (buggy)
REPO_ROOT = Path(__file__).parent.parent

# Another Python script (different buggy)
REPO_ROOT = Path(__file__).parent.parent.parent
```

The postmortem describes a real incident: "Path bug in three Python scripts. Three incorrect `.parent`. Didn't check path for 30 seconds in terminal — coded blindly."

**Fix (STORY-94):** Single `paths.py` module. Walk upward to `pyproject.toml`. Assert existence on import. No guessing.

---

## 5. The `pult` Roadmap in Detail

### 5.1 Phase 0: Immediate Mitigation (STORY-97)

1. **Invert prompt order:** Phase instruction + HARD STOP at top, context below
2. **Lock WRAP:** Explicit `Do NOT write code` at top of WRAP prompt
3. **Loud RVC failure:** Exit 1 with `ERROR [MISSING_CLI]` instead of silent warn

### 5.2 Phase 1: Python Wrapper (STORY-95)

```python
class Pult:
    def run(self, story_id: str, phase: str) -> str:
        result = subprocess.run(
            ["bash", str(BOOTSTRAP), "--phase", phase, story_id],
            capture_output=True, text=True
        )
        if result.returncode != 0 or result.stderr.strip():
            ec = self.classifier.classify(result.stderr, result.returncode)
            payload = {...}
            log_path.write_text(json.dumps(payload, indent=2))
            raise PultError(payload)
        return result.stdout
```

**Key innovation:** stderr is NEVER dropped. Every error is classified, logged, and surfaced.

### 5.3 Phase 2: Artifact Injection (STORY-96)

After a successful phase run, `pult` injects a blank template artifact into the story file:

```html
<!-- l3:phase=engage story=STORY-XX status=pending version=1 -->
plan_summary: |
  (agent fills in)
files_to_touch:
  - (list files)
risks: none
<!-- /l3:phase=engage -->
```

This eliminates format drift. The agent fills in values; the structure is guaranteed.

### 5.4 Phase 3: Absorption (STORY-99)

`session_bootstrap.sh` is fully ported to Python:

```python
class PromptBuilder:
    def _get_issue(self, story_id: str) -> str:      # rvc issue STORY-XX
    def _get_specs(self, story_id: str) -> str:      # rvc context STORY-XX
    def _get_decisions(self) -> str:                  # reads DECISIONS.md
    def _get_gotchas(self) -> str:                    # reads GOTCHAS.md
    def _get_git_state(self) -> dict:                 # git branch, status, log
    def build(self, story_id: str, phase: str) -> str: # assembles prompt
```

The bash script becomes a one-liner shim or is deleted entirely.

---

## 6. Recommendations for ADLAI Team

### 6.1 Run the Manual Test Today

```bash
cd /home/lexx/Documents/ADLAI
bash adlai-vault/00_Project/session_bootstrap.sh --phase sync STORY-87 | head -80
```

Check:
1. Does the prompt contain real issue content (not `"(issue not found)"`)?
2. Does `## PHASE: SYNC` appear in the first 10 lines?
3. Does the HARD STOP appear before line 10?
4. Does `rvc` appear in the prompt (proving linked specs were resolved)?

This 30-second test validates the entire L5→L2→L0 chain.

### 6.2 Do Not Add Features Until EPIC-15 Closes

The dependency graph is strict:

```
STORY-94 (paths.py)
    └── STORY-95 (pult wrapper)
            ├── STORY-96 (artifact injection)
            │       └── STORY-99 (absorption)
            └── STORY-97 (prompt fix)
                    └── STORY-98 (E2E tests)
                            └── STORY-99 (absorption)
```

Trying to build conductor L3 sub-graphs, graph DB backends, or parallel DAG execution before these basics work is premature optimization.

### 6.3 Migrate Flow Docs to Conductor Vault

The flow-related specs and stories (WORKFLOW_*.md, EPIC-15, STORY-87, STORY-92-99) conceptually belong to the meta-project (Conductor+RVC), not the product (ADLAI). They have been copied to `~/X/TEAMFLOW/conductor/docs/flow/` in this report's file manifest.

**Suggested next step:** Create a `conductor-vault` (or rename `rvc-vault` to `conductor-vault`) and move these stories there. ADLAI vault should contain only ADLAI business logic (retrieval, citation, corpus, evaluation, verticals).

### 6.4 Measure Prompt Size Per Phase

After STORY-97 (inverted prompts) and STORY-96 (artifact injection), measure:

```bash
# Size by phase
bash session_bootstrap.sh --phase sync STORY-XX | wc -l
bash session_bootstrap.sh --phase engage STORY-XX | wc -l
bash session_bootstrap.sh --phase act STORY-XX | wc -l
bash session_bootstrap.sh --phase wrap STORY-XX | wc -l
```

Target: each phase < 500 lines. If any phase exceeds this, the context is still too bloated and needs Phase 4 optimization (lazy loading).

---

## 7. Conclusion

ADLAI is the proving ground for the Conductor+RVC stack. The integration has been productive but has revealed real gaps:

1. **L3 Phase Gating** is the critical missing piece. Without it, Conductor's Act node is a single monolithic invocation that LLMs can freely ignore.
2. **`pult` is the right abstraction** — a control panel that sits between Conductor (L4) and the vault (L2), managing phase transitions, error classification, and artifact injection.
3. **The 6 fragilities** are all fixable within 2 weeks of focused work (EPIC-15).
4. **The test gap** (103 tests on temp vault vs. 0 on real vault) is the biggest risk. STORY-98 must validate that the real vault + real rvc + real git state produce correct prompts.

**Bottom line:** The stack is 80% built. The remaining 20% (L3 gating, pult, real-vault tests) is what separates a demo from a daily-driver orchestration system.

---

*End of Analysis*


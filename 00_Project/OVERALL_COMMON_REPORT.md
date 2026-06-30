# Overall Common Report: Conductor + RVC + ADLAI Flow Integration

*Generated: 2026-06-28*
*Scope: Architecture review and development plan for the unified agent orchestration stack*

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Three Systems](#2-the-three-systems)
3. [ADLAI Flow Deep-Dive](#3-adlai-flow-deep-dive)
4. [Cross-System Integration Map](#4-cross-system-integration-map)
5. [Consolidated Issues & Gaps](#5-consolidated-issues--gaps)
6. [Extended Development Plan](#6-extended-development-plan)
7. [Epics and Stories Registry](#7-epics-and-stories-registry)
8. [Appendix: File Manifest](#8-appendix-file-manifest)

---

## 1. Executive Summary

This report synthesizes findings from three interdependent projects:

| System | Role | Location | Maturity |
|--------|------|----------|----------|
| **Conductor** | L4 LangGraph orchestration harness | `~/Q/conductor` | Beta — core pipeline works, PlanReviser stub |
| **RVC Protocol** | L2 vault/artifact management CLI | `~/Q/vault-protocol` | Production-ready with security debt |
| **ADLAI** | Target product (legal AI RAG) + L3/L5 flow integration | `~/Documents/ADLAI` | Active dev, 103 tests, flow layer being hardened |

**The Big Picture:** ADLAI is the first real-world consumer of the Conductor+RVC stack. The integration has revealed 6 systemic workflow fragilities (documented in `CHECKPOINT_POSTMORTEM.md`) that span all three systems. Fixing them requires coordinated changes across the entire stack.

**Key Insight:** The weakest layer is not Conductor's LangGraph (L4) or RVC's vault CLI (L2) — it is **L3 Phase Gating** (SYNC→ENGAGE→ACT→WRAP), which currently lives in a bash script (`session_bootstrap.sh`) with no structured error handling, no artifact injection for 3 of 4 phases, and prompt-order bugs that cause LLMs to ignore phase boundaries.

---

## 2. The Three Systems

### 2.1 Conductor (`~/Q/conductor`)

**What it does:** Model-agnostic agent orchestration via LangGraph. Pipeline: `plan → review → approve → act → qa → plan_reviser → commit`.

**Current state (from code audit):**
- Graph compiles and checkpoints to SQLite
- Human approval gate works via `interrupt()`
- Worker abstraction supports claude, gemini, qwen, opencode
- RVC context integration works (`--extra-context` / `--no-context`)
- **Critical gap:** `plan_reviser_node` is a stub — cannot autonomously recover from QA failures
- **Security gap:** `qa_node` uses `shell=True`
- **Performance gap:** Sequential act execution (no DAG parallelism)

**Files:** `pipeline.py`, `workers.py`, `schema.py`, `projects_config.py`, `__main__.py`

### 2.2 RVC Protocol (`~/Q/vault-protocol`)

**What it does:** Local-first, Obsidian-native issue tracking. Markdown + YAML frontmatter + folder-based status lanes.

**Current state (from code audit):**
- `rvc-cli.py` (430 lines) — issue CRUD, lifecycle transitions, search, rescan
- `rvcd.py` (290 lines) — FastMCP daemon exposing CLI as tools
- `vault-restructure.py` (696 lines) — idempotent vault normalization, wikilink wrapping, tag inference, MAP.md generation
- **Critical gap:** `shell=True` everywhere in `rvc-cli.py`
- **Performance gap:** `O(n²)` vault traversal (`find_file_by_id()` walks entire vault on every call)
- **Robustness gap:** Ad-hoc YAML parser (manual string splitting)

**Files:** `rvc-cli.py`, `rvcd.py`, `vault-restructure.py`, `rvc-sync.py`

### 2.3 ADLAI (`~/Documents/ADLAI`)

**What it does:** Bilingual (AR/EN) legal AI assistant with hybrid RAG, citation verification, and attorney review queue.

**Current state (from vault audit):**
- 1,153 markdown files in vault
- 115+ stories/epics tracked
- 103 integration tests pass (but run against temp vault fixtures)
- Backend: Python FastAPI + Postgres + pgvector
- Frontend: Vue 3 SPA
- **Flow layer:** `session_bootstrap.sh` (436 lines) generates phase-specific prompts

---

## 3. ADLAI Flow Deep-Dive

### 3.1 The OSI-Style Layer Model

ADLAI's workflow team developed a 6-layer enforcement model (documented in `WORKFLOW_LAYERS.md`):

```
L5 — Bootstrap    session_bootstrap.sh    ✅ BUILT
L4 — Conductor    Plan→Act→QA→Commit       ✅ BUILT (~/Q/conductor)
L3 — Phase Gating SYNC→ENGAGE→ACT→WRAP     🟡 PARTIAL (SYNC/ENGAGE done, ACT/WRAP broken)
L2 — Artifacts    STATE.json, DECISIONS.md  ✅ BUILT
L1 — Tool Sandbox Permissions per phase     ⚠️ PARTIAL
L0 — Model        The LLM itself            ⚠️ PARTIAL
```

**The L3 gap is the critical path.** Without it, Conductor's Act node receives a monolithic prompt that the LLM can freely ignore. The L3 layer splits one Conductor Act invocation into 4 separate LLM calls, each with hard STOP boundaries.

### 3.2 The 6 Systemic Fragilities (from CHECKPOINT_POSTMORTEM)

| # | Problem | Layer | Impact | Status |
|---|---------|-------|--------|--------|
| 1 | Prompt Context Bloat — HARD STOP at line 385 | L5 | LLM plans implementation before reading constraints | Being fixed in STORY-97 |
| 2 | Silent Diagnostic Failures — stderr swallowed | L5 | No error classification, no vault persistence | Being fixed in STORY-95 |
| 3 | Synthetic Test Vacuum — 103 tests on temp vault | L3/L5 | No E2E validation against real vault | Being fixed in STORY-98 |
| 4 | Missing Phase Runner — no `pult` entry point | L5 | Manual 4-phase chaining | Being fixed in EPIC-15 |
| 5 | Manual Artifact Generation — only SYNC auto-injected | L3 | Format drift, gate failures | Being fixed in STORY-96 |
| 6 | WRAP Code Mutability — no explicit code-mutation ban | L3 | LLM "fixes" files during wrap | Being fixed in STORY-97 |

### 3.3 The `pult` Project

`pult` (Russian: "control panel") is the emerging L5 entry point that wraps `session_bootstrap.sh` and eventually absorbs it.

**Architecture (from WORKFLOW_PULT.md):**

```
pult run STORY-XX              # full SYNC→ENGAGE→ACT→WRAP
pult run STORY-XX --sync       # SYNC only
pult run STORY-XX --engage     # ENGAGE (fails w/o SYNC ready)
pult status STORY-XX           # show artifact state
pult logs STORY-XX             # show recent logs
```

**Implementation phases:**
- **Phase 0 (STORY-97):** Fix prompt order + harden WRAP in bash script
- **Phase 1 (STORY-95):** Python wrapper + error classifier around bash script
- **Phase 2 (STORY-96):** Structured artifact injection for all 4 phases
- **Phase 3 (STORY-99):** Full absorption — bash script retired, `PromptBuilder` in Python

### 3.4 Current Implementation Status

| Phase | Prompt | Auto-Artifact | Validation Gate | Tests | Status |
|-------|--------|---------------|-----------------|-------|--------|
| SYNC | ✅ | ✅ (STORY-93) | ✅ HARD STOP | 12+ | 🟢 Built |
| ENGAGE | ✅ | ✅ (sync artifact) | ✅ gates on ready | 6+ | 🟢 Built |
| ACT | ⚠️ Written but broken | ❌ Not implemented | ⚠️ Broken (`$STORY_FILE` not set) | ❌ None | 🔴 Blocked |
| WRAP | ⚠️ Written but broken | ❌ Not implemented | ⚠️ Broken (`$STORY_FILE` not set) | ❌ None | 🔴 Blocked |

**Known bug (STORY-87):** `session_bootstrap.sh:126-128` only sets `$STORY_FILE` for `sync|engage`. ACT and WRAP always fail immediately because the story file variable is empty.

### 3.5 Artifact Format

The L3 artifact is embedded in the story file under `## L3 Artifacts`:

```markdown
<!-- l3:phase=sync story=STORY-XX status=ready version=1 -->
Timestamp: 2026-06-16T12:00:00Z
Git branch: prompts
Git head: a1b2c3d
Dirty files: 2
Context Summary: ...
Readiness: ready
Missing: none
Boundary:
- No implementation was performed during SYNC.
<!-- /l3:phase=sync -->
```

**Design principle:** "Make the artifact boring, deterministic, and easy to gate."

---

## 4. Cross-System Integration Map

### 4.1 Data Flow

```
Human in Obsidian          AI via MCP/conductor          Background cron
     │                              │                            │
     └────────┬─────────────────────┴────────────────────────────┘
              │
     ┌────────▼──────────────────────────────────────────────────┐
     │  ADLAI Vault (~/Documents/ADLAI/adlai-vault)              │
     │    10_Issues/02_Active/STORY-87.md                        │
     │    00_Project/STATE.json                                  │
     │    00_Project/DECISIONS.md                                │
     │    00_Project/GOTCHAS.md                                  │
     └────────┬──────────────────────────────────────────────────┘
              │
     ┌────────▼────────┐    ┌──────────────┐    ┌──────────────┐
     │ session_bootstrap│───→│   pult.py    │───→│  conductor   │
     │    .sh (L5)      │    │  (L5 wrapper)│    │   (L4)       │
     └─────────────────┘    └──────────────┘    └──────────────┘
              │                       │                │
              │                       │                │
     ┌────────▼────────┐    ┌────────▼────────┐   ┌───▼──────────┐
     │   rvc CLI       │    │  ErrorClassifier│   │  qwen worker │
     │ (L2 vault ops)  │    │  JSON logs      │   │  plan/act/qa │
     └─────────────────┘    └─────────────────┘   └──────────────┘
```

### 4.2 Tool Boundaries

| Tool | Owns | Calls | Replaced by |
|------|------|-------|-------------|
| `conductor` | L4 graph, checkpointing, human gate | `pult` (future) or `session_bootstrap.sh` (current) | Nothing — stays as outer ring |
| `pult` (planned) | L5 phase runner, error classification, artifact injection | `session_bootstrap.sh` (Phase 1), then nothing (Phase 3) | Absorbs `session_bootstrap.sh` |
| `session_bootstrap.sh` | Prompt generation, artifact auto-write (SYNC only) | `rvc`, `git` | `pult.py PromptBuilder` (Phase 3) |
| `rvc` | L2 issue CRUD, vault rescan, context assembly | Filesystem | Nothing — stays as vault CLI |

### 4.3 Path Resolution Chain

**Current fragility:** Every component guesses paths independently.

```python
# session_bootstrap.sh
VAULT="${VAULT:-/home/lexx/Documents/ADLAI/adlai-vault}"  # hardcoded

# Python scripts (buggy)
REPO_ROOT = Path(__file__).parent.parent  # breaks when run from unexpected cwd
```

**Fix (STORY-94):** Centralized `backend/app/services/paths.py`:
- `REPO_ROOT` — found by walking up to `pyproject.toml`
- `VAULT` — `REPO_ROOT / "adlai-vault"` (overridable via env)
- `BOOTSTRAP` — `VAULT / "00_Project" / "session_bootstrap.sh"`
- Asserts `BOOTSTRAP.exists()` on import

---

## 5. Consolidated Issues & Gaps

### 5.1 Critical (P0) — Blocks reliable operation

| # | Issue | System | File | Fix Target |
|---|-------|--------|------|------------|
| 1 | `shell=True` in QA node | Conductor | `pipeline.py:424` | STORY-008 |
| 2 | `shell=True` in rvc-cli git ops | RVC | `rvc-cli.py:9,65,73` | STORY-013 |
| 3 | PlanReviser is a stub | Conductor | `pipeline.py:445` | STORY-009 |
| 4 | `$STORY_FILE` not set for ACT/WRAP | ADLAI Flow | `session_bootstrap.sh:126` | STORY-97 |
| 5 | Path resolution is copy-pasted, fragile | ADLAI Flow | 3 Python scripts | STORY-94 |
| 6 | No centralized phase runner | ADLAI Flow | N/A | EPIC-15 |

### 5.2 High (P1) — Significant friction

| # | Issue | System | Fix Target |
|---|-------|--------|------------|
| 7 | O(n²) vault traversal | RVC | STORY-013 |
| 8 | Ad-hoc YAML parser | RVC | STORY-014 |
| 9 | No artifact injection for ENGAGE/ACT/WRAP | ADLAI Flow | STORY-96 |
| 10 | Tests run on temp vault, not real vault | ADLAI Flow | STORY-98 |
| 11 | RVC context fetched twice per cycle | Conductor | STORY-012 |
| 12 | No unit tests for Conductor | Conductor | STORY-010 |
| 13 | ACT/WRAP prompt HARD STOP at line 385 | ADLAI Flow | STORY-97 |

### 5.3 Medium (P2) — Nice to have

| # | Issue | System | Fix Target |
|---|-------|--------|------------|
| 14 | Sequential act execution (no DAG parallelism) | Conductor | STORY-011 |
| 15 | Bulk node wired but unused | Conductor | RECOMMENDATIONS.md P5 |
| 16 | WorkerResult.error truncation mismatch | Conductor | workers.py |
| 17 | `_extract_stream_json` drops malformed lines silently | Conductor | workers.py |
| 18 | No atomic ID generation (race condition) | RVC | STORY-013 |
| 19 | WRAP allows implicit code mutation | ADLAI Flow | STORY-97 |

---

## 6. Extended Development Plan

### 6.1 Phase 0: Stop the Bleeding (This Week)

**Goal:** Fix critical bugs that block any reliable flow execution.

| Task | Story | Effort | Owner |
|------|-------|--------|-------|
| Fix `$STORY_FILE` for ACT/WRAP in bootstrap | STORY-97 | 15 min | ADLAI Flow |
| Create `paths.py` with strict assertions | STORY-94 | 1 hour | ADLAI Flow |
| Replace `shell=True` in QA node | STORY-008 | 30 min | Conductor |
| Replace `shell=True` in rvc-cli | STORY-013 | 1 hour | RVC |
| RVC pre-flight fails loudly (exit 1) | STORY-97 | 15 min | ADLAI Flow |

### 6.2 Phase 1: Observability & Control (Next 2 Weeks)

**Goal:** Build `pult` wrapper so errors are visible and classified.

| Task | Story | Effort | Owner |
|------|-------|--------|-------|
| Pult Phase 1: Python wrapper + ErrorClassifier | STORY-95 | 4 hours | ADLAI Flow |
| Pult Phase 2: Artifact injection for all 4 phases | STORY-96 | 1 day | ADLAI Flow |
| Invert prompt structure (HARD STOP first) | STORY-97 | 2 hours | ADLAI Flow |
| Real-vault integration tests | STORY-98 | 1 day | ADLAI Flow |

### 6.3 Phase 2: Intelligence & Hardening (Next Month)

**Goal:** Make Conductor autonomous and RVC production-ready.

| Task | Story | Effort | Owner |
|------|-------|--------|-------|
| Real PlanReviser with QA diagnosis | STORY-009 | 2–3 days | Conductor |
| Unit test foundation (Conductor) | STORY-010 | 2 days | Conductor |
| Parallel DAG execution | STORY-011 | 3 days | Conductor |
| RVC context caching | STORY-012 | 30 min | Conductor |
| Vault indexing (JSON cache) | STORY-013 | 1 day | RVC |
| Real YAML parser | STORY-014 | 4 hours | RVC |
| Pult Phase 3: Absorb bash script | STORY-99 | 2 days | ADLAI Flow |

### 6.4 Phase 3: Polish & Scale (Next Quarter)

**Goal:** Full integration maturity.

| Task | Effort | Owner |
|------|--------|-------|
| Auto-transition RVC issue after conductor commit | 1 day | Both |
| Web dashboard for run history & plan visualization | 1–2 weeks | Conductor |
| Graph DB backend for RVC (Neo4j/SQLite graph) | 1–2 weeks | RVC |
| Structured contracts (JSONSchema) for plan nodes | 2 days | Conductor |
| Self-healing QA (flaky test detection) | 3 days | Conductor |

---

## 7. Epics and Stories Registry

### 7.1 Conductor Project (`~/Q/conductor`)

| ID | Title | Status | Priority |
|----|-------|--------|----------|
| EPIC-002 | Conductor v0.2 — Production Hardening & Intelligence | To Do | High |
| STORY-008 | Eliminate `shell=True` | To Do | Critical |
| STORY-009 | Real PlanReviser with QA Log Diagnosis | To Do | Critical |
| STORY-010 | Unit Test Foundation | To Do | High |
| STORY-011 | Parallel DAG Execution | To Do | High |
| STORY-012 | RVC Context Caching | To Do | Medium |

### 7.2 RVC Protocol (`~/Q/vault-protocol`)

| ID | Title | Status | Priority |
|----|-------|--------|----------|
| EPIC-001 | The RVC Local-First Protocol | In Progress | Critical |
| STORY-002 | RVC Scaffolder | To Do | High |
| STORY-004 | Obsidian Templater Suite | To Do | Medium |
| STORY-013 | RVC CLI Security & Performance Hardening | To Do | High |
| STORY-014 | Replace Ad-Hoc YAML Parser | To Do | Medium |

### 7.3 ADLAI Flow Integration (`~/Documents/ADLAI`)

| ID | Title | Status | Priority |
|----|-------|--------|----------|
| EPIC-15 | Workflow Orchestration & Pult Integration | To Do | P0 |
| STORY-87 | Workflow Layered Architecture (L3 phase gating) | Active | P1 |
| STORY-92 | L3 MVP-1: SYNC-only phase prompt | Done | P1 |
| STORY-93 | L3 MVP-2: SYNC artifact + ENGAGE gate | Done | P1 |
| STORY-94 | Core Path Resolution (`paths.py`) | To Do | P0 |
| STORY-95 | Pult Phase 1: Python Wrapper & Error Classifier | To Do | P0 |
| STORY-96 | Pult Phase 2: Structured Artifact Injection | To Do | P1 |
| STORY-97 | Fix ACT/WRAP Prompt Gates | To Do | P1 |
| STORY-98 | Real-Vault Integration Testing | To Do | P1 |
| STORY-99 | Pult Phase 3: Absorption (Deprecate Bash) | To Do | P2 |

---

## 8. Appendix: File Manifest

All flow-related files have been consolidated into `~/Q/conductor/docs/flow/`:

```
docs/flow/
├── stories/
│   ├── EPIC-15.md                          # Workflow Orchestration & Pult Integration
│   ├── STORY-87.md                         # Workflow Layered Architecture (Active)
│   ├── STORY-87-backlog.md                 # Earlier backlog version
│   ├── STORY-87-verification.md            # Verification notes
│   ├── STORY-92.md                         # L3 MVP-1: SYNC-only phase
│   ├── STORY-93.md                         # L3 MVP-2: SYNC artifact + ENGAGE gate
│   ├── STORY-94.md                         # Core Path Resolution
│   ├── STORY-95.md                         # Pult Phase 1: Wrapper + Error Classifier
│   ├── STORY-96.md                         # Pult Phase 2: Artifact Injection
│   ├── STORY-97.md                         # Fix ACT/WRAP Prompt Gates
│   ├── STORY-98.md                         # Real-Vault Integration Testing
│   └── STORY-99.md                         # Pult Phase 3: Absorption
├── specs/
│   ├── WORKFLOW.md                         # Session Ritual (4 phases)
│   ├── WORKFLOW_PULT.md                    # Pult architecture & strategy
│   ├── WORKFLOW_LAYERS.md                  # OSI-style enforcement model
│   └── WORKFLOW_DOMAIN.md                  # Domain root node
├── meta/
│   ├── CHECKPOINT.md                       # STORY-87 test checkpoint
│   └── CHECKPOINT_POSTMORTEM.md            # 6 systemic fragilities
└── scripts/
    └── session_bootstrap.sh                # L5 bootstrap script (436 lines)
```

**Original locations preserved in ADLAI vault** for backward compatibility. The copies in `docs/flow/` are the canonical reference for cross-system planning.

---

## 9. Recommendations

1. **Execute Phase 0 immediately.** The `$STORY_FILE` bug (STORY-97) and `shell=True` issues (STORY-008, STORY-013) are 15-minute fixes that eliminate entire classes of failures.

2. **Prioritize STORY-94 before any other ADLAI flow work.** Path resolution is foundational. Every subsequent story (95-99) imports from `paths.py`. Without it, new code repeats the same fragility.

3. **Run the CHECKPOINT.md manual test.** `bash session_bootstrap.sh --phase sync STORY-87 | head -80` — verify the prompt contains real data from the vault. This is the fastest way to validate the entire L5→L2 chain.

4. **Do not expand scope beyond EPIC-15 until it closes.** The 6 child stories (94-99) form a strict dependency graph. Attempting to add features (e.g., conductor L3 sub-graph, graph DB backend) before the basics work is how the current mess accumulated.

5. **Consider unifying RVC and Conductor vaults.** Currently there are two vaults: `~/Q/vault-protocol/rvc-vault` (meta-project) and `~/Documents/ADLAI/adlai-vault` (product). The flow docs live in ADLAI vault but conceptually belong to the meta-project. A single unified vault with domain tags (`#meta`, `#adlai`) might reduce cognitive overhead.

---

*End of Report*

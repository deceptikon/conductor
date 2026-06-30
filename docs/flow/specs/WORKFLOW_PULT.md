---
type: architecture
domain: workflow
status: draft
tags: [cicd, citation, cli, data-quality, database, frontend, infra, ingestion, llm, observability, orchestrator, pult, routing, s6, testing, vertical, workflow]
created: 2026-06-16
related: "[[WORKFLOW_DOMAIN]], [[WORKFLOW]], [[L0_MODEL]], [[L5_BOOTSTRAP]]"
---

# Workflow Pult — Control Panel for the Orchestration Harness

> **Пульт управления** (pult = control panel) — a lightweight CLI + Python
> toolkit that replaces `session_bootstrap.sh` as the main entry point for
> running workflow sessions.

---

## Purpose

`session_bootstrap.sh` generates prompts. `pult` does that AND:

1. **Runs phases** — SYNC, ENGAGE, ACT, WRAP sequentially or individually
2. **Collects all output** — stdout (prompt) + stderr (errors/warnings) — never to /dev/null
3. **Classifies errors** — GATE_FAIL, GATE_PENDING, RVC_ABSENT, GIT_ERR, etc.
4. **Writes structured logs** — JSON logs in `adlai-vault/00_Project/logs/`
5. **Manages artifacts** — injects predecessor artifacts so the chain can proceed
6. **Feeds back to prompt** — tells the bootstrap what went wrong so the LLM can improve it

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ pult (CLI entry point)                                      │
│   backend/app/services/pult.py                              │
│                                                             │
│   Usage:                                                    │
│     pult run [[STORY-87]]           # full SYNC→ENGAGE→ACT→WRAP │
│     pult run [[STORY-87]] --sync    # SYNC only                 │
│     pult run [[STORY-87]] --engage  # ENGAGE (fails w/o SYNC)   │
│     pult status [[STORY-87]]        # show artifact state       │
│     pult logs [[STORY-87]]          # show recent logs          │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase Runner                                                │
│   backend/app/services/workflow_runner.py                   │
│                                                             │
│   • Calls session_bootstrap.sh --phase <phase> <story_id>   │
│   • Captures stdout + stderr                               │
│   • Classifies stderr lines into error categories           │
│   • Validates stdout structure (gate pass/fail markers)     │
│   • Returns PhaseResult                                     │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Artifact Ingestor (optional)                                │
│                                                             │
│   • After SYNC passes → promote artifact to ready           │
│   • After ENGAGE passes → inject ENGAGE artifact block      │
│   • After ACT passes → inject ACT artifact block            │
│   • Makes the chain proceedable without manual intervention │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Log Writer                                                  │
│                                                             │
│   • adlai-vault/00_Project/logs/flow_<story>_<ts>.json      │
│   • adlai-vault/00_Project/logs/errors_<story>_<ts>.json    │
│   • Structured: phase, exit_code, stderr, classified_errors │
└─────────────────────────────────────────────────────────────┘
```

---

## Error Classification

Every line of stderr is classified:

| Class | Meaning | Example |
|-------|---------|---------|
| `OK` | No errors | — |
| `GATE_FAIL` | Predecessor phase artifact missing | "No SYNC artifact found" |
| `GATE_PENDING` | Predecessor phase not ready | "status=pending (expected ready)" |
| `RVC_ABSENT` | rvc CLI not in PATH | "rvc CLI not found" → issue content = placeholder |
| `GIT_ERR` | git command failed | "not a git repository" |
| `TIMEOUT` | Subprocess killed after 30s | — |
| `SCRIPT_MISSING` | session_bootstrap.sh not found | — |
| `UNKNOWN` | Unrecognized stderr line | — |

---

## Two Operating Modes

### Mode 1: PoC (current)

`session_bootstrap.sh` stays as-is. Pult wraps it:
- Calls the script, captures output
- Classifies errors
- Writes logs
- Optionally injects artifacts so the chain can proceed

Benefits: minimal changes, no risk of breaking existing tests.

### Mode 2: Absorption (next)

`session_bootstrap.sh` is **fully absorbed** into `pult`:
- The bash script logic moves into Python
- Shell parsing (grep/sed for artifacts) → Python regex via story_io module
- Prompt generation → Python string templates
- pult becomes the single entry point

Benefits: testable, type-safe, no bash quoting hell, easier to evolve.

---

## Relationship to Existing Tools

| Tool | Role | pult replaces? |
|------|------|----------------|
| `session_bootstrap.sh` | Prompt generator | Yes (Mode 2) |
| `rvc issue` | Issue CRUD | No — pult delegates to rvc for issue ops |
| `rvc context` | Linked specs | No — delegates |
| `conductor` | Outer orchestration (L4) | No — pult is inner (L5), conductor calls pult |
| `uv run pytest` | QA gate | No — pult tells agent to run it |

---

## Vault Integration

All pult output goes to vault:

```
adlai-vault/00_Project/
├── logs/
│   ├── flow_STORY-87_20260616_143000.json   # full phase run log
│   └── errors_STORY-87_20260616_143000.json # classified errors only
├── STATE.json                                  # updated by pult (current phase)
└── phase_logs/                                 # optional: per-phase stdout
    ├── sync_STORY-87_20260616_143000.txt
    └── engage_STORY-87_20260616_143000.txt
```

---

## What pult does NOT do

- Execute the LLM prompt — that's opencode/qwen/conductor's job
- Make git commits — that's the agent's job in WRAP phase
- Replace rvc — pult reads issues, doesn't manage them
- Run tests — pult generates the prompt that tells the agent to run tests

pult is the **control panel**, not the **engine**.

---

## Critical Management Plan (Implementation Strategy)

To transition from the current fragile bash scripts to the robust Pult architecture and address the workflow pains outlined in the recent postmortem (`adlai-vault/00_Project/CHECKPOINT_POSTMORTEM.md`), the following phased plan must be executed sequentially. This plan prioritizes immediate stability, followed by observability, testing, and finally, architectural consolidation.

### 🔴 Phase 0: Immediate Mitigation (Stop the Bleeding)
**Focus:** Prevent path bugs (blind `.parent` traversal) and enforce strict LLM phase boundaries to stop unauthorized code modifications during read-only phases.

1. **Invert the Prompt Structure (`session_bootstrap.sh`):**
   - **Current Flaw:** The `## PHASE` constraints, rules, and the `HARD STOP` instruction are at the bottom of the prompt (line 385+). The LLM processes the issue context first and begins formulating implementation plans before reading the constraints.
   - **Action:** Move the `## PHASE: SYNC — READ ONLY`, `## PHASE: ENGAGE`, etc., blocks to the *absolute top* of the generated output. The LLM must read the constraints before reading the large context blocks (STATE, DECISIONS, GOTCHAS, CODE STATE).

2. **Lock Down WRAP (`session_bootstrap.sh`):**
   - **Current Flaw:** The WRAP prompt tells the agent to "verify git status" and "commit", but lacks an explicit prohibition against modifying code. Agents sometimes attempt last-minute fixes during WRAP.
   - **Action:** Add a highly visible `Do NOT write or modify any code during this phase.` directive at the top of the WRAP phase prompt instructions.

3. **Implement Robust Path Resolution (`backend/app/services/paths.py`):**
   - **Current Flaw:** Three Python scripts recently failed due to incorrect `.parent` relative path assumptions when executed from unexpected working directories.
   - **Action:** Create a centralized `paths.py` module.
     - Implement a function `get_repo_root()` that crawls upwards from `__file__` to locate `pyproject.toml`.
     - Define `BOOTSTRAP_SCRIPT = get_repo_root() / "adlai-vault" / "00_Project" / "session_bootstrap.sh"`.
     - Add strict startup assertions: `assert BOOTSTRAP_SCRIPT.exists(), "Fatal: Cannot locate session_bootstrap.sh"`
     - Refactor existing scripts to import and use `paths.py` instead of calculating relative paths.

### 🟡 Phase 1: Establish the Control Panel (Implement Pult Mode 1)
**Focus:** Gain observability and log errors. Stop relying on silent stderr drops.

1. **Develop the Pult Core (`backend/app/services/pult.py`):**
   - Build a Python CLI (using `argparse` or `typer`) that acts as a wrapper around the existing `session_bootstrap.sh`.
   - **Execution Engine:** Use `subprocess.run(..., capture_output=True, text=True)`. Never discard stderr.

2. **Implement Error Classification (`backend/app/services/workflow_runner.py`):**
   - Create a regex-based classifier to parse the captured `stderr`.
   - Define strict error classes and map regex patterns to them:
     - `GATE_FAIL`: "No SYNC artifact found", "Prior phases not ready"
     - `RVC_ABSENT`: "rvc CLI not found in PATH"
     - `GIT_ERR`: "fatal: not a git repository"
     - `TIMEOUT`: Ensure `subprocess.run` has a sensible timeout (e.g., 30s) to catch hanging commands.

3. **Structured Logging (`backend/app/services/logger.py`):**
   - Ensure `pult` writes structured JSON logs for every run to `adlai-vault/00_Project/logs/`.
   - Log schema must include: `timestamp`, `story_id`, `phase_requested`, `exit_code`, `classified_errors` (array), and `stderr_raw`.

4. **Standardize Artifact Extraction/Injection (Optional for Mode 1, Required for Mode 2):**
   - Instead of relying solely on the LLM to format the artifact markdown perfectly, have `pult` intercept the LLM's raw response, extract the YAML/Markdown artifact block, and safely append it to the story file using Python.

### 🟢 Phase 2: Ensure Ground Truth (Integration Testing on Real Vault)
**Focus:** Validate the workflow against the real environment (`adlai-vault`), not just isolated mock vaults. The current 103 tests exist in a vacuum.

1. **Promote the Test Fixture (`backend/tests/integration/conftest.py`):**
   - Create a new fixture (e.g., `real_vault_session`) that runs tests against a cloned snapshot or a controlled, active copy of `VAULT=adlai-vault`, rather than a completely synthetic `temp_vault`.

2. **Simulate a Full Loop (`backend/tests/integration/test_pult_e2e.py`):**
   - Create an end-to-end test using `pult.py` that walks a dummy issue (e.g., `STORY-TEST-01`) through the entire state machine: `SYNC -> ENGAGE -> ACT -> WRAP`.
   - Assert that phase gates block execution appropriately (e.g., trying to run `ACT` before `ENGAGE` fails with a specific `GATE_FAIL` log entry).
   - Assert that the final state leaves a properly formatted commit and artifact history.

### 🔵 Phase 3: Consolidation (Pult Mode 2 - Absorption)
**Focus:** Retire brittle bash scripts entirely and transition to a fully type-safe, observable Python architecture.

1. **Deprecate Bash:**
   - Port all logic from `session_bootstrap.sh` directly into Python methods within `pult.py` and supporting service modules.
   - Replace bash subshells (`git ...`, `rvc ...`) with dedicated Python wrapper functions (`backend/app/services/git_ops.py`, `backend/app/services/rvc_ops.py`) that handle subprocess execution and error checking robustly.

2. **Pythonic Prompt Generation (`backend/app/services/prompt_builder.py`):**
   - Use Python string templates or a templating engine (like Jinja2) for constructing the LLM prompts. This makes the prompt structure easier to read, test, and version.

3. **Strict Validation Pre-Flight:**
   - Before a prompt is even constructed or sent to the LLM, `pult` must use Python to parse the story file and explicitly validate the presence, syntax, and `ready` status of previous phase artifacts. If validation fails, `pult` terminates immediately and logs the structural error.

### 🟣 Phase 4: Context Optimization (De-bloating the Prompt)
**Focus:** Address the "awfulness" of the generated prompt. Currently, `session_bootstrap.sh` dumps the *entire* universe (STATE, DECISIONS, GOTCHAS, full git logs, all specs) indiscriminately, overwhelming the LLM and diluting the primary instruction.

1. **Phase-Specific Context Gathering:**
   - Context gathering must be localized to the phase that actually needs it.
   - **SYNC:** Needs `STATE.json`, the raw issue, and high-level decisions to understand the landscape.
   - **ENGAGE:** Needs only the target issue, linked `20_Specs`, and the SYNC artifact to formulate a plan.
   - **ACT:** Needs the ENGAGE plan and specific target files. It *does not* need the global GOTCHAS or high-level ROADMAP.
   - **WRAP:** Needs the diff, test results, and the ACT artifact. It *does not* need the original spec.

2. **Lazy/Dynamic Loading via Pult:**
   - Instead of concatenating strings via bash `cat`, `pult` should dynamically assemble the payload.
   - Example: If an issue specifically tags `domain: database`, `pult` should only inject `DB-Schema.md`, omitting the rest of the specs directory.

3. **Context Condensation:**
   - Instead of passing raw, unedited logs, use `pult` to format them into strict, bulleted lists before injection.
   - Example: Instead of a 50-line `git status --short`, format it to `Modified: X files (main.py, test_app.py)` unless the phase specifically requests file-level granularity.

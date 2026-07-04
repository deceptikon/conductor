---
aliases:
  - STORY-97
type: story
status: To Do
priority: P1
created: 2026-06-16
updated: 2026-06-16
id: STORY-97
epic: "[[EPIC-15]]"
title: Fix ACT/WRAP Prompt Gates in session_bootstrap.sh
tags: [bootstrap, phase-gating, workflow]
related: "[[EPIC-15]], [[STORY-98]], [[L3_PHASE_GATING]], [[CHECKPOINT_POSTMORTEM]]"
domain: workflow_meta
domain_tags: ["story", "testing"]
---

# STORY-97: Fix ACT/WRAP Prompt Gates in `session_bootstrap.sh`

## Context

The postmortem identifies two concrete prompt defects in `session_bootstrap.sh`
that cause LLM phase-blending and unauthorized code mutation:

**Problem 1 — Prompt Context Bloat & Order (Problem 1 in postmortem):**
The SYNC phase currently outputs ~385 lines of context (issue + specs +
decisions + gotchas + code state) *before* the phase instruction (HARD STOP).
By the time the model reaches "Do NOT write code", it has already processed
the entire implementation problem and begun planning. The phase instruction
must appear **first**, before any context payload.

**Problem 6 — WRAP Phase Code Mutability (Problem 6 in postmortem):**
The WRAP prompt says "verify git status, git commit" but does not include an
explicit, hard-forbidden instruction against modifying code. Models routinely
attempt to "fix" issues they notice during WRAP. The fix must be explicit and
positioned at the top of the WRAP prompt — not buried in a bullet list.

**Note:** A quick scan confirms the ACT phase already has `"Do NOT write
code"` in the gate and the WRAP prompt already has it in the bullet list.
This story's goal is to harden the *position* (always first) and *strength*
(HARD STOP wording) of these guards, not to add new logic.

## Goal

1. **Restructure all 4 phase prompts** so the PHASE instruction and HARD STOP
   boundary appear in the **first 5 lines** of generated output — before the
   context payload (issue, specs, decisions, git state).
2. **Harden the WRAP HARD STOP** with an explicit code-mutation prohibition
   that appears at the top of the prompt, formatted as a bold alert.
3. **Add a pre-flight RVC check** that fails loudly (exit 1, structured message
   to stderr) instead of the current non-fatal `WARN:` line.
4. **Verify the `$STORY_FILE` fix** from [[STORY-87]] Phase 1 is active and working
   for ACT/WRAP phases.

## Prerequisites

- [[STORY-87]] Phase 1 (`$STORY_FILE` bug fix) must be **Done**.
- [[STORY-94]] (`paths.py`) should be **Done** or **In Progress** (paths.py
  provides canonical `VAULT_DIR` used by bootstrap).

## Acceptance Criteria

- [ ] In `session_bootstrap.sh`, for every phase (`sync`, `engage`, `act`, `wrap`):
  - The phase header line (e.g., `## PHASE: SYNC`) is output **before** issue content, specs, decisions, and git state
  - The HARD STOP instruction appears within the first 5 lines after the phase header
- [ ] WRAP prompt first block contains:
  ```
  ⛔ HARD STOP: You are in WRAP phase.
  DO NOT modify any source code files.
  DO NOT run test commands that modify state.
  Your ONLY allowed actions: git commit, rvc issue review, write DECISIONS/GOTCHAS.
  ```
- [ ] RVC pre-flight check: if `command -v rvc` fails, the script exits 1 and writes to stderr:
  ```
  ERROR [MISSING_CLI]: rvc not found in PATH. Cannot resolve issue content.
  Hint: ensure rvc is installed and on PATH before running session_bootstrap.sh.
  ```
  (This replaces the current non-fatal `WARN:` message.)
- [ ] **ACT and WRAP phases execute successfully with real story files** (verifies STORY-87 Phase 1 fix)
- [ ] **G1 gate:** `session_bootstrap.sh` validates story file exists and has required frontmatter (`type`, `status`, `id`) before generating prompt for any phase; exits 1 with structured stderr if invalid
- [ ] **G2.5 gate:** RVC pre-flight fails loudly (exit 1, structured stderr) instead of silent WARN
- [ ] **G3 gate:** each phase validates predecessor artifacts exist with `status=ready` before emitting prompt; exits 1 with `GATE_FAIL` if not
- [ ] The SYNC prompt change is backward-compatible: existing gate validation logic (artifact detection, status checks) is unchanged
- [ ] Integration tests in `backend/tests/integration/test_phase_*.py` continue to pass after the restructure
- [ ] New unit test assertions in `backend/tests/unit/test_bootstrap_prompt_structure.py`:
  - SYNC prompt: phase header appears before line 10 of output
  - ENGAGE prompt: HARD STOP appears before line 10 of output
  - ACT prompt: HARD STOP appears before line 10 of output
  - WRAP prompt: code-mutation prohibition appears before line 10 of output
  - RVC missing: exit code is 1, stderr contains `ERROR [MISSING_CLI]`
  - **G1 gate: missing story file → exit 1, stderr contains `ERROR [INVALID_PATH]`**
  - **G3 gate: missing predecessor artifact → exit 1, stderr contains `ERROR [GATE_FAIL]`**
- [ ] `uv run pytest backend/tests/unit/test_bootstrap_prompt_structure.py -q` exits 0

## Edge Cases & Error Scenarios

| Scenario | Expected Behaviour |
|----------|-------------------|
| Story file exists but `status` is not `ready` for ENGAGE | G3 fails → exit 1, stderr: `ERROR [GATE_FAIL]: SYNC artifact status=pending (expected ready)` |
| Story file exists but frontmatter lacks `id` | G1 fails → exit 1, stderr: `ERROR [INVALID_PATH]: missing required frontmatter field 'id'` |
| `rvc` is in PATH but `rvc issue` returns non-zero | G2.5 passes (rvc is reachable), but issue content may be empty; script continues with fallback text |
| Phase is `act` but ENGAGE artifact is missing | G3 fails before any prompt generation |
| WRAP phase and git working tree is dirty | Prompt includes warning; script does NOT exit (WRAP is allowed to commit dirty tree) |

## Non-Functional Requirements

- **Backward Compatibility:** Existing `SYNC` and `ENGAGE` tests must pass without modification
- **Performance:** No additional subprocess calls; gates are pure file/regex checks
- **Observability:** Every gate failure writes structured stderr that `ErrorClassifier` (STORY-95) can parse

## Implementation Notes

The restructure approach: move the phase-specific `cat << 'PROMPT'` block that
emits the HARD STOP to **precede** the `printf` calls that inject issue content
and specs. The content payload follows the instruction block.

Before (current order for SYNC):
```
[header: mission context]
[git state]
[issue content]
[linked specs]
[decisions]
[gotchas]
[code state]
[phase instruction + HARD STOP]   ← buried at end
```

After (target order for all phases):
```
[PHASE: <NAME> — HARD STOP instruction]   ← FIRST
[issue content]
[linked specs]
[decisions]
[gotchas]
[git state]
[artifact target]
```

For the RVC pre-flight, replace:
```bash
if ! command -v rvc &>/dev/null; then
  echo "WARN: rvc CLI not found..." >&2
fi
```
With:
```bash
if ! command -v rvc &>/dev/null; then
  printf 'ERROR [MISSING_CLI]: rvc not found in PATH. Cannot resolve issue content.\n' >&2
  printf 'Hint: ensure rvc is installed and on PATH before running session_bootstrap.sh.\n' >&2
  exit 1
fi
```

## Files to Touch

| File | Action |
|------|--------|
| `adlai-vault/00_Project/session_bootstrap.sh` | **EDIT** — restructure prompt order + harden WRAP |
| `backend/tests/unit/test_bootstrap_prompt_structure.py` | **CREATE** |

## Definition of Done

- Phase instruction is always the first content block in every phase prompt
- WRAP HARD STOP explicitly forbids code modification in the first 5 lines
- RVC pre-flight fails loudly with exit 1 on missing CLI
- Existing integration tests still pass
- New prompt structure tests pass
- `ruff check` not applicable (bash), manual review of diff

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->

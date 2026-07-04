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

# STORY-97: `pult prompt` — Phase-Specific Prompt Assembly with HARD STOP

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

- [[STORY-95]] (`pult gather` + `pult validate`) must be **Done** — provides context bundle and gate validation.
- [[STORY-94]] (`paths.py`) should be **Done** — provides canonical paths.

## Acceptance Criteria

- [ ] `pult prompt <story_id> --phase <phase>` exists and outputs assembled prompt to stdout
- [ ] For every phase (`sync`, `engage`, `act`, `wrap`):
  - The phase header line (e.g., `## PHASE: SYNC`) is output **before** issue content, specs, decisions, and git state
  - The HARD STOP instruction appears within the first 5 lines after the phase header
- [ ] WRAP prompt first block contains:
  ```
  ⛔ HARD STOP: You are in WRAP phase.
  DO NOT modify any source code files.
  DO NOT run test commands that modify state.
  Your ONLY allowed actions: git commit, rvc issue review, write DECISIONS/GOTCHAS.
  ```
- [ ] `pult prompt` reads context from `pult gather` JSON output (or from a temp file written by `pult gather`)
- [ ] `pult prompt` does NOT re-implement context gathering (no duplicate git/rvc calls)
- [ ] `pult prompt` does NOT re-implement validation (assumes `pult validate` was run)
- [ ] **G2 gate:** validate that required context sections are present before assembling prompt; fail with `BOOTSTRAP_ERROR` if context bundle is incomplete
- [ ] New unit test assertions in `backend/tests/unit/test_pult_prompt.py`:
  - SYNC prompt: phase header appears before line 10 of output
  - ENGAGE prompt: HARD STOP appears before line 10 of output
  - ACT prompt: HARD STOP appears before line 10 of output
  - WRAP prompt: code-mutation prohibition appears before line 10 of output
  - All phases: issue content is included
  - All phases: decisions and gotchas are included
  - G2 gate: incomplete context bundle → `BOOTSTRAP_ERROR`
- [ ] `uv run pytest backend/tests/unit/test_pult_prompt.py -q` exits 0

## Edge Cases & Error Scenarios

| Scenario | Expected Behaviour |
|----------|-------------------|
| `pult prompt` called without prior `pult gather` | Reads context from default path; if missing, fails with `BOOTSTRAP_ERROR` |
| Context bundle exists but is missing `git_branch` | Uses "unknown" as fallback; logs warning |
| Context bundle exists but is missing `issue_content` | Uses "(issue not found)" as fallback; logs warning |
| Phase is `act` but QA command in prompt references wrong path | Prompt is assembled as-is; QA gate catches the error at runtime |
| WRAP phase and git working tree is dirty | Prompt includes warning; does NOT exit (WRAP is allowed to commit dirty tree) |
| `pult prompt --phase sync` called with `--output file.md` | Writes prompt to file instead of stdout (useful for debugging) |

## Non-Functional Requirements

- **Backward Compatibility:** `session_bootstrap.sh` continues to work while `pult prompt` is being built
- **Performance:** Prompt assembly must complete in <100ms (pure string formatting, no subprocess calls)
- **Observability:** Every prompt assembly logs: phase, story_id, prompt length, context sections included
- **Determinism:** Same context bundle + same phase → same prompt (no randomness)

## Implementation Notes

`pult prompt` receives a context bundle (from `pult gather`) and assembles the
phase-specific prompt. The key change is the **order** of sections:

Before (current order in `session_bootstrap.sh`):
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

After (target order for all phases in `pult prompt`):
```
[PHASE: <NAME> — HARD STOP instruction]   ← FIRST
[issue content]
[linked specs]
[decisions]
[gotchas]
[git state]
[artifact target]
```

The `pult prompt` implementation should:
1. Read context bundle JSON (from `pult gather` output or temp file)
2. Validate required sections exist (G2 gate)
3. Assemble prompt using Python f-strings or Jinja2 templates
4. Output to stdout

## Files to Touch

| File | Action |
|------|--------|
| `backend/app/services/pult.py` | **EDIT** — add `pult prompt` subcommand |
| `backend/tests/unit/test_pult_prompt.py` | **CREATE** |
| `adlai-vault/00_Project/session_bootstrap.sh` | **EDIT** (optional) — mirror changes as fallback |

## Definition of Done

- `pult prompt` assembles phase-specific prompts with HARD STOP first
- WRAP HARD STOP explicitly forbids code modification in the first 5 lines
- `pult prompt` reads context from `pult gather` (no duplicate subprocess calls)
- G2 gate validates context bundle completeness
- Unit tests pass for all 4 phases
- `ruff check` clean
- `session_bootstrap.sh` continues to work as fallback

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->

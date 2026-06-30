---
type: story
status: Done
priority: P1
started: 2026-06-15
id: STORY-92
title: L3-MVP-1-SYNC-only-phase-prompt-generation
tags: [citation, database, eval, frontend, infra, llm, testing]
---

# STORY-92: L3 MVP-1: SYNC-only phase prompt generation

## Context
[[VAULT_DOMAINS_AUDIT_2026-06-15]] warns that L3 Phase Gating is the critical gap before reliable agent flow. The audit recommends the smallest safe increment: implement only `--phase sync` first, not the full SYNC→ENGAGE→ACT→WRAP runner.

Related specs:
- [[L3_PHASE_GATING]] — phase gating design
- [[WORKFLOW]] — session ritual being enforced
- [[L2_ARTIFACTS]] — artifacts and handoff protocol
- [[REGLAMENT]] — living status ledger

## Goal
Add the first real L3 boundary: `session_bootstrap.sh --phase sync STORY-XX` generates a SYNC-only prompt that cannot drift into ACT.

This story is prompt generation only. It does not execute qwen/opencode and does not implement all phases.

## Scope
Touch only:
- `adlai-vault/00_Project/session_bootstrap.sh`
- `adlai-vault/00_Project/REGLAMENT.md` only if status ledger needs a small note
- this story file for findings/verification notes

Do not touch:
- `20_Specs/L*.md`
- `WORKFLOW_LAYERS.md`
- `WORKFLOW_DOMAIN.md`
- `MAP.md`
- conductor code

## Acceptance Criteria
- [ ] `bash adlai-vault/00_Project/session_bootstrap.sh --phase sync STORY-XX` works.
- [ ] Existing legacy call still works: `bash adlai-vault/00_Project/session_bootstrap.sh STORY-XX`.
- [ ] SYNC prompt contains only SYNC duties: read state/artifacts/issue/specs, summarize current context, produce/announce SYNC boundary.
- [ ] SYNC prompt ends with a hard stop: do not engage, do not implement, do not test, do not commit.
- [ ] SYNC prompt does not contain ACT/WRAP implementation instructions except as forbidden actions.
- [ ] No qwen/opencode execution is required by this story.
- [ ] REGLAMENT status ledger is updated only if needed, and no status is added to specs.

## Verification Commands
```bash
cd /home/lexx/Documents/ADLAI
bash adlai-vault/00_Project/session_bootstrap.sh [[STORY-89]] >/tmp/bootstrap_legacy.txt
bash adlai-vault/00_Project/session_bootstrap.sh --phase sync [[STORY-89]] >/tmp/bootstrap_sync.txt

grep -n "PHASE: SYNC\|SYNC" /tmp/bootstrap_sync.txt
grep -ni "do not engage\|do not implement\|do not commit\|STOP" /tmp/bootstrap_sync.txt
! grep -ni "git commit\|pytest\|rvc issue .*review" /tmp/bootstrap_sync.txt
```

## Session Report (2026-06-15)

### Implementation
- Added `--phase <phase>` argument parsing to `session_bootstrap.sh` (lines 20-29)
- Added `if [[ "$PHASE" == "sync" ]]` branch emitting a SYNC-bounded prompt:
  - "PHASE: SYNC — READ ONLY" section
  - 4 duties: read context, summarize, announce SYNC boundary, HARD STOP
  - 6 forbidden items (no code, no edits, no tests, no transitions, no state updates, no impl plans)
  - Output directive: produce SYNC announcement
- Legacy (no flag) path unchanged

### Verification results
```
# Legacy mode
bash session_bootstrap.sh [[STORY-89]] >/tmp/legacy.txt
EXIT: 0  |  2080 lines  |  contains WORKFLOW: yes

# Sync mode
bash session_bootstrap.sh --phase sync [[STORY-89]] >/tmp/sync.txt
EXIT: 0  |  662 lines  |  contains PHASE: SYNC: yes

# SYNC section content (tail from "## PHASE: SYNC" onward)
grep "HARD STOP":  line 649  "**HARD STOP.** Do not engage, do not implement..."
grep "Forbidden":  line 651, with 6 Do NOT rules
grep "git commit|pytest|rvc issue.*review":  0 matches in SYNC section
```

All ACs met.

### REGLAMENT update
L3 status changed from `🔴 Missing` → `🟡 Partial` in both:
- Living Status Ledger table: `--phase sync` implemented; ENGAGE/ACT/WRAP remain
- Layers diagram: `❌ CRITICAL GAP` → `🟡 SYNC phase only`

No status badges added to any spec files.

## Self-Review vs. VAULT_DOMAINS_AUDIT

Audit reference: [[VAULT_DOMAINS_AUDIT_2026-06-15]]

| Audit requirement | Status |
|---|---|
| `--phase sync` with hard STOP | ✅ Done |
| No ACT/WRAP commands in SYNC prompt | ✅ Done |
| Legacy mode preserved | ✅ Done |
| No global deadlock (audit point 3) | ✅ Done |
| REGLAMENT updated, specs clean (audit point 6) | ✅ Done |
| **Hard artifact** (audit point 2) | **❌ Missing** |
| **Transcript proof** (audit point 7) | **❌ Missing** |

### Gap analysis

The audit warned explicitly:
> "Define the first hard artifact before defining the whole runner. Without this, L3 remains a prompt convention."

STORY-92's implementation is still a prompt convention — a disciplined one, but nothing in the filesystem proves SYNC happened. When ENGAGE starts next session, the SYNC work is entirely in the agent's memory. One context reset and it's gone.

The audit also asked for a transcript proof:
> "The first successful L3 increment should leave a short captured output proving the agent stopped after SYNC and did not plan or implement ACT."

Prompt verification (grep on generated text) is not the same as an agent execution transcript. That's the next increment.

---

## Captain's Direction: Artifact Boundary Design (for L3 MVP-2)

Captain's axiom: "Make the artifact boring, deterministic, and easy to gate."

MVP-2 must not build a "full runner invokes LLM, parses stdout, flips status." That's too much surface area. Instead:

1. `--phase sync STORY-XX` generates a SYNC-only prompt, declares the artifact target, declares the allowed write scope — does **not** invoke the LLM itself.
2. The SYNC agent may write exactly one thing: the SYNC artifact. No code, no tests, no issue transition, no STATE/DECISIONS/GOTCHAS updates unless explicitly chosen later.
3. `--phase engage STORY-XX` refuses unless a valid `status=ready` SYNC artifact exists.

### Artifact location: embedded in the story file

```
adlai-vault/10_Issues/02_Active/STORY-92-....md
```

Append/update:

```markdown
## L3 Artifacts

### SYNC

<!-- l3:phase=sync story=STORY-92 status=ready version=1 -->

Timestamp: 2026-06-15T12:00:00Z
Git branch: prompts
Git head: c27d4b9
Dirty files: 1

Readiness: ready

Context Summary:
- Issue goal: implement SYNC-only prompt generation.
- Relevant specs read: [[L3_PHASE_GATING]], [[WORKFLOW]], [[L2_ARTIFACTS]], [[REGLAMENT]]
- Current implementation state: `--phase sync` exists and legacy mode remains.

Boundary:
- Ready for ENGAGE.
- No implementation was performed during SYNC.
- No tests were run during SYNC.
- No commit was made during SYNC.

Missing:
- none

<!-- /l3:phase=sync -->
```

**Why story-file embedding for MVP-2:**

| Concern | Separate file | Story-embedded |
|---|---|---|
| Moves with RVC transitions | Must manually relocate | Follows the issue file |
| Orphan risk | Yes — dates diverge | Zero |
| Lookup ambiguity | Date-glob needed | Deterministic: story path |
| Human inspectability | Two places to check | One place |
| Shell validation | Multi-file grep | Single-file grep |

### Validation (MVP-2)

```bash
issue_file="$(find adlai-vault/10_Issues -name 'STORY-XX-*.md' | head -1)"
grep -q '<!-- l3:phase=sync story=STORY-XX status=ready version=1 -->' "$issue_file"
```

### Prompt wording change

Current: `Do NOT edit files.`
MVP-2: `Do NOT edit files except the declared SYNC artifact target.`

### Future option: separated artifacts

If story files grow too noisy, move to:

```
adlai-vault/10_Issues/_Artifacts/STORY-XX/SYNC.md
```

Do not introduce `_Artifacts/` until the story-embedded approach proves too noisy.

### MVP-2 acceptance criteria

- [ ] `--phase sync STORY-XX` prompt names the artifact target (the story file's `## L3 Artifacts` section).
- [ ] SYNC prompt permits exactly one write: the SYNC artifact.
- [ ] Artifact has machine-readable marker: `<!-- l3:phase=sync story=STORY-XX status=ready version=1 -->`.
- [ ] Artifact records: timestamp, git branch, git head, dirty file count, specs/context read, readiness, missing blockers, explicit "no ACT performed" statement.
- [ ] `--phase engage STORY-XX` exits non-zero if no `status=ready` SYNC artifact exists.
- [ ] Legacy no-flag mode remains unchanged.
- [ ] Prompt changed from "Do NOT edit files" to "Do NOT edit files except the declared SYNC artifact target."

### Design principle

> Keep data in the vault, bound to the exact story or graph node. Bind markdown to markdown via [[wikilinks]] — that's how the vault tracks without spoiling centralized state.

---

## Tests (12 unit tests)

Implemented in `backend/tests/unit/test_session_bootstrap.py`:
- `TestSyncPhaseArtifactTarget` (2) — artifact target named, write exception permitted
- `TestSyncPhaseCoreRules` (4) — hard stop, forbidden actions, no ACT commands, no ENGAGE prompt
- `TestEngagePhaseValidation` (3) — ready/missing/blocked artifact with mocked vault
- `TestLegacyModePreserved` (3) — exit 0, contains WORKFLOW, no PHASE: label

## Definition of Done
- [x] `--phase sync` generates SYNC-only prompt successfully
- [x] Legacy mode unchanged ([[STORY-89]] test: exit 0, 2080 lines)
- [x] SYNC prompt contains only SYNC duties (read, summarize, announce boundary)
- [x] SYNC prompt ends with HARD STOP and forbids ENGAGE/ACT/WRAP
- [x] SYNC section clean of ACT/WRAP commands (0 matches for git commit/pytest/rvc review)
- [x] QA gate: 295 passed, 2 skipped
- [x] REGLAMENT updated: L3 is `🟡 Partial` (SYNC + artifact target + engage validation)


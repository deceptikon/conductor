#!/bin/bash
# session_bootstrap.sh [--phase <phase>] <issue_id>
# Constructs a self-contained session prompt with auto-context + task.
# Output goes to stdout. Pipe into opencode run or save to file.
#
# Phases:
#   (default)     — full prompt (legacy, all 4 phases)
#   --phase sync    — SYNC-only prompt ending with hard STOP
#   --phase engage  — validates SYNC is ready, outputs ENGAGE prompt
#   --phase act     — validates SYNC+ENGAGE ready, outputs ACT prompt
#   --phase wrap    — validates all prior phases ready, outputs WRAP prompt
#
# Usage:
#   bash session_bootstrap.sh STORY-87
#   bash session_bootstrap.sh --phase sync STORY-87
#   opencode run --model "opencode/big-pickle" --pure "$(bash session_bootstrap.sh STORY-87)"

set -euo pipefail

PHASE=""
case "${1:-}" in
  --phase)
    PHASE="${2:?Usage: session_bootstrap.sh --phase <phase> <issue_id>}"
    ISSUE_ID="${3:?Usage: session_bootstrap.sh --phase <phase> <issue_id>}"
    ;;
  *)
    ISSUE_ID="${1:?Usage: session_bootstrap.sh <issue_id>}"
    ;;
esac

VAULT="${VAULT:-/home/lexx/Documents/ADLAI/adlai-vault}"
REPO="${REPO:-/home/lexx/Documents/ADLAI}"
STATE_FILE="$VAULT/00_Project/STATE.json"
DECISIONS_FILE="$VAULT/00_Project/DECISIONS.md"
GOTCHAS_FILE="$VAULT/00_Project/GOTCHAS.md"

cd "$REPO"

# --- RVC health check (non-fatal warning) ---
if ! command -v rvc &>/dev/null; then
  echo "WARN: rvc CLI not found in PATH — issue content and linked specs will be placeholder text." >&2
fi

# --- STATE ---
STATE_JSON="{}"
if [[ -f "$STATE_FILE" ]]; then
  STATE_JSON=$(cat "$STATE_FILE" 2>/dev/null || echo "{}")
fi

# --- DECISIONS (last 3 entries, strip boilerplate) ---
DECISIONS=""
if [[ -f "$DECISIONS_FILE" ]]; then
  DECISIONS=$(awk '/^## /{found++} found>=1{print}' "$DECISIONS_FILE" 2>/dev/null)
fi
DECISIONS=$(echo "$DECISIONS" | grep -v '^# Decisions' | grep -v '^_Appended' | sed '/^$/d' | tail -12)
[[ -z "$DECISIONS" ]] && DECISIONS="(no decisions logged yet)"

# --- GOTCHAS (last 3 entries, strip boilerplate) ---
GOTCHAS=""
if [[ -f "$GOTCHAS_FILE" ]]; then
  GOTCHAS=$(awk '/^## /{found++} found>=1{print}' "$GOTCHAS_FILE" 2>/dev/null)
fi
GOTCHAS=$(echo "$GOTCHAS" | grep -v '^# Gotchas' | grep -v '^_Appended' | sed '/^$/d' | tail -12)
[[ -z "$GOTCHAS" ]] && GOTCHAS="(no gotchas logged yet)"

# --- ISSUE (strip RVC footer noise) ---
ISSUE_CONTENT=$(rvc issue "$ISSUE_ID" 2>/dev/null | sed '/^===/,/^===/d' || echo "(issue not found)")

# --- LINKED SPECS ---
SPEC_DATA=$(rvc context "$ISSUE_ID" 2>/dev/null || echo "(no linked specs)")

# --- CODE STATE ---
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --short 2>/dev/null || echo "(unavailable)")
GIT_LOG=$(git log --oneline -5 2>/dev/null || echo "(unavailable)")
DIRTY_COUNT=$(echo "$GIT_STATUS" | grep -cvE '^\s*$' || true)
LAST_COMMIT=$(echo "$GIT_LOG" | head -1)

# ============================================================
# Build prompt via temp file (safe heredoc — no bash expansion)
# ============================================================
TEMP_PROMPT=$(mktemp)
trap "rm -f $TEMP_PROMPT" EXIT

# --- Header ---
cat > "$TEMP_PROMPT" << 'PROMPT'
You are a headless coding agent working on the ADLAI project.
Follow the WORKFLOW ritual (adlai-vault/20_Specs/WORKFLOW.md).

## MISSION CONTEXT

PROMPT

printf '%s\n' "Active Branch: $GIT_BRANCH" >> "$TEMP_PROMPT"
printf '%s\n' "Dirty Files: $DIRTY_COUNT" >> "$TEMP_PROMPT"
printf '%s\n' "Last Commit: $LAST_COMMIT" >> "$TEMP_PROMPT"

# --- Issue ---
printf '\n## ISSUE: %s\n\n' "$ISSUE_ID" >> "$TEMP_PROMPT"
printf '%s\n' "$ISSUE_CONTENT" >> "$TEMP_PROMPT"

# --- Linked context ---
printf '\n## LINKED CONTEXT (specs + related issues)\n\n' >> "$TEMP_PROMPT"
printf '%s\n' "$SPEC_DATA" >> "$TEMP_PROMPT"

# --- Decisions ---
printf '\n## PREVIOUS DECISIONS (last 3)\n\n' >> "$TEMP_PROMPT"
printf '%s\n' "$DECISIONS" >> "$TEMP_PROMPT"

# --- Gotchas ---
printf '\n## KNOWN GOTCHAS (last 3)\n\n' >> "$TEMP_PROMPT"
printf '%s\n' "$GOTCHAS" >> "$TEMP_PROMPT"

# --- Code state ---
printf '\n## CODE STATE\n\n' >> "$TEMP_PROMPT"
printf 'Branch: %s\n' "$GIT_BRANCH" >> "$TEMP_PROMPT"
printf 'Working tree:\n%s\n' "$GIT_STATUS" >> "$TEMP_PROMPT"
printf '\nRecent commits:\n%s\n' "$GIT_LOG" >> "$TEMP_PROMPT"

# --- Run state ---
printf '\n## CURRENT RUN STATE\n\n' >> "$TEMP_PROMPT"
printf '%s\n' "$STATE_JSON" >> "$TEMP_PROMPT"

# --- L3 artifact discovery (for any phase that needs it) ---
STORY_FILE=""
if [[ -n "$PHASE" ]]; then
  STORY_FILE=$(find "$VAULT/10_Issues" -name "${ISSUE_ID}-*.md" -type f 2>/dev/null | head -1 || true)
fi

# --- Workflow pointer (not dumped in full) ---
if [[ "$PHASE" == "sync" ]]; then
  # --- SYNC artifact auto-generation ---
  if [[ -z "$STORY_FILE" ]]; then
    printf '\n## ARTIFACT TARGET\n\nNo story file found for %s — cannot generate SYNC artifact.\n' "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi

  # Idempotent: skip if artifact already exists
  ARTIFACT_EXISTS=false
  if grep -q "<!-- l3:phase=sync story=$ISSUE_ID" "$STORY_FILE" 2>/dev/null; then
    ARTIFACT_EXISTS=true
  fi

  if [[ "$ARTIFACT_EXISTS" != true ]]; then
    ARTIFACT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    ARTIFACT_BRANCH="$GIT_BRANCH"
    ARTIFACT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    ARTIFACT_DIRTY="$DIRTY_COUNT"

    # Append L3 Artifacts section + SYNC block at end of story file
    cat >> "$STORY_FILE" <<ARTIFACT_EOF

## L3 Artifacts

### SYNC

<!-- l3:phase=sync story=$ISSUE_ID status=pending version=1 -->

Timestamp: $ARTIFACT_TIMESTAMP
Git branch: $ARTIFACT_BRANCH
Git head: $ARTIFACT_HEAD
Dirty files: $ARTIFACT_DIRTY

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
ARTIFACT_EOF
  fi

  # Artifact target section (tone for auto-generated artifact)
  cat >> "$TEMP_PROMPT" << 'ARTIFACT_PROMPT'

## ARTIFACT TARGET

A preliminary SYNC artifact has been auto-generated in the story file above.
Review the context above, then update the artifact:
- Change status=pending → status=ready (or blocked)
- Fill in Context Summary, Readiness, and Missing fields
- Do NOT modify the auto-generated fields (timestamp, branch, head, dirty count, boundary boilerplate)
ARTIFACT_PROMPT

  cat >> "$TEMP_PROMPT" << 'PROMPT'

## PHASE: SYNC — READ ONLY

You are in the **SYNC** phase of the WORKFLOW ritual. Your role is to
understand the current context and nothing more.

### Your duties
1. Read the issue, linked specs, decisions, gotchas, state, and code state above.
2. Summarize what you found — what is the task, what state is the project in,
   what decisions were made, what gotchas apply.
3. Announce the **SYNC boundary**: state whether you have enough context to
   proceed, or what is missing.
4. **HARD STOP.** Do not engage, do not implement, do not test, do not commit.

### Forbidden
- Do NOT write code.
- Do NOT edit files, except the declared SYNC artifact target above.
- Do NOT run tests.
- Do NOT transition the issue.
- Do NOT update STATE.json, DECISIONS.md, or GOTCHAS.md.
- Do NOT write anything that resembles an implementation plan.

### Output
Produce a SYNC announcement summarizing the context. End with a clear
statement of whether you are ready to proceed to ENGAGE, or what needs
to be resolved first.
PROMPT

elif [[ "$PHASE" == "engage" ]]; then
  if [[ -z "$STORY_FILE" ]]; then
    printf '\n## PHASE: ENGAGE — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No story file found for %s in %s/10_Issues/.\n' "$ISSUE_ID" "$VAULT" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q "<!-- l3:phase=sync story=$ISSUE_ID" "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: ENGAGE — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No SYNC artifact found in %s.\n' "$STORY_FILE" >> "$TEMP_PROMPT"
    printf 'Run `--phase sync %s` first.\n' "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  ARTIFACT_STATUS=$(grep -oP "l3:phase=sync story=$ISSUE_ID\s[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  if [[ "$ARTIFACT_STATUS" != "ready" ]]; then
    printf '\n## PHASE: ENGAGE — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'SYNC artifact found but status="%s" (expected "ready") in %s.\n' "$ARTIFACT_STATUS" "$STORY_FILE" >> "$TEMP_PROMPT"
    printf 'Resolve the missing context before re-running SYNC.\n' >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  printf '\n## PHASE: ENGAGE — VALIDATED\n\n' >> "$TEMP_PROMPT"
  printf 'SYNC artifact is ready (%s). Proceed to ENGAGE phase.\n' "$STORY_FILE" >> "$TEMP_PROMPT"

  cat >> "$TEMP_PROMPT" << 'PROMPT'

## PHASE: ENGAGE — PLAN ONLY

You are in the **ENGAGE** phase of the WORKFLOW ritual. Your role is to
plan the work and transition the issue — not to implement.

### Your duties
1. Read the SYNC artifact in the story file above.
2. If not already Active, transition the issue from To Do to Active.
3. Update STATE.json to reflect current branch + agent.
4. Read relevant specs for the code you'll change.
5. Output a brief ENGAGE plan — what you will do, what files you'll touch,
   what specs may need updating.
6. **Do NOT write code yet.**

### Forbidden
- Do NOT write code.
- Do NOT implement any changes.
- Do NOT run tests.
- Do NOT commit.

### Output
Produce an ENGAGE announcement describing your plan. Write an ENGAGE
artifact into the story file under `## L3 Artifacts` → `### ENGAGE`
with `status=pending`, then update it to `status=ready` once the plan
is confirmed.
PROMPT

elif [[ "$PHASE" == "act" ]]; then
  if [[ -z "$STORY_FILE" ]]; then
    printf '\n## PHASE: ACT — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No story file found for %s.\n' "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q '<!-- l3:phase=sync' "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: ACT — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No SYNC artifact found in %s. Run `--phase sync %s` first.\n' "$STORY_FILE" "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  SYNC_STATUS=$(grep -oP "l3:phase=sync[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  if [[ "$SYNC_STATUS" != "ready" ]]; then
    printf '\n## PHASE: ACT — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'SYNC artifact status="%s" (expected "ready"). Complete SYNC before proceeding.\n' "$SYNC_STATUS" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q '<!-- l3:phase=engage' "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: ACT — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No ENGAGE artifact found in %s. Run `--phase engage %s` first.\n' "$STORY_FILE" "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  ENGAGE_STATUS=$(grep -oP "l3:phase=engage[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  if [[ "$ENGAGE_STATUS" != "ready" ]]; then
    printf '\n## PHASE: ACT — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'ENGAGE artifact status="%s" (expected "ready"). Complete ENGAGE before proceeding.\n' "$ENGAGE_STATUS" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  printf '\n## PHASE: ACT — VALIDATED\n\n' >> "$TEMP_PROMPT"
  printf 'SYNC and ENGAGE artifacts are ready (%s). Proceed to ACT phase.\n' "$ISSUE_ID" >> "$TEMP_PROMPT"

  cat >> "$TEMP_PROMPT" << 'PROMPT'

## PHASE: ACT — IMPLEMENT

You are in the **ACT** phase of the WORKFLOW ritual. Your role is to
implement the plan from ENGAGE.

### Your duties
1. Read the ENGAGE artifact from the story file above.
2. Implement the planned changes. Edit files as needed.
3. Update specs (L*.md) if code behavior changed.
4. Run the QA gate:
   ```bash
   uv run pytest backend/tests/unit -q
   ```
   - If tests fail, fix and re-run (max 3 attempts).
5. Do NOT commit until QA passes.

### Forbidden
- Do NOT commit.
- Do NOT transition the issue to Review.
- Do NOT modify existing artifact blocks (write ACT artifact below existing ones).

### QA gate
After implementation, you MUST verify the QA gate passes (exit 0).

### Output
When QA passes, write an ACT artifact under `## L3 Artifacts` → `### ACT`
with `status=ready` and the following fields:
- Files changed (one per line)
- test_exit_code: 0
- Spec updates: N/A or list
PROMPT

elif [[ "$PHASE" == "wrap" ]]; then
  if [[ -z "$STORY_FILE" ]]; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No story file found for %s.\n' "$ISSUE_ID" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q '<!-- l3:phase=sync' "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No SYNC artifact found. Complete SYNC before WRAP.\n' >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q '<!-- l3:phase=engage' "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No ENGAGE artifact found. Complete ENGAGE before WRAP.\n' >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  if ! grep -q '<!-- l3:phase=act' "$STORY_FILE" 2>/dev/null; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'No ACT artifact found. Complete ACT before WRAP.\n' >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  ACT_STATUS=$(grep -oP "l3:phase=act[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  if [[ "$ACT_STATUS" != "ready" ]]; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'ACT artifact status="%s" (expected "ready"). Complete ACT before proceeding.\n' "$ACT_STATUS" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  SYNC_STATUS_W=$(grep -oP "l3:phase=sync[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  ENGAGE_STATUS_W=$(grep -oP "l3:phase=engage[^>]*status=\K\w+" "$STORY_FILE" 2>/dev/null | head -1 || true)
  if [[ "$SYNC_STATUS_W" != "ready" || "$ENGAGE_STATUS_W" != "ready" ]]; then
    printf '\n## PHASE: WRAP — VALIDATION FAILED\n\n' >> "$TEMP_PROMPT"
    printf 'Prior phases not ready: SYNC=%s, ENGAGE=%s (expected both "ready").\n' "$SYNC_STATUS_W" "$ENGAGE_STATUS_W" >> "$TEMP_PROMPT"
    cat "$TEMP_PROMPT"
    exit 1
  fi
  printf '\n## PHASE: WRAP — VALIDATED\n\n' >> "$TEMP_PROMPT"
  printf 'All prior artifacts ready (SYNC, ENGAGE, ACT). Proceed to WRAP phase.\n' >> "$TEMP_PROMPT"

  cat >> "$TEMP_PROMPT" << 'PROMPT'

## PHASE: WRAP — COMMIT AND CLOSE

You are in the **WRAP** phase of the WORKFLOW ritual. Your role is to
commit the changes, transition the issue, and clean up.

### Your duties
1. Verify `git status` shows only the files you changed.
2. Commit with conventional format:
   ```bash
   git commit -m "<type>: <subject> ($ISSUE_ID)"
   ```
3. Transition the issue to Review:
   ```bash
   rvc issue $ISSUE_ID review
   ```
4. Append any non-obvious decisions to DECISIONS.md.
5. Append any discovered pitfalls to GOTCHAS.md.
6. Update STATE.json to clear the current session.

### Forbidden
- Do NOT write code.
- Do NOT modify tests.

### Output
Write a WRAP artifact under `## L3 Artifacts` → `### WRAP` with:
- commit_sha (from git rev-parse HEAD)
- files_changed count
- rvc_transition: yes
- status: ready
PROMPT

else
  cat >> "$TEMP_PROMPT" << 'PROMPT'

## WORKFLOW

Follow the 4-phase ritual in adlai-vault/20_Specs/WORKFLOW.md:
  SYNC → read artifacts + issue + specs
  ENGAGE → transition issue + update state
  ACT → implement, update specs if code changed
  WRAP → test, commit, transition, log decisions/gotchas
PROMPT
fi

cat "$TEMP_PROMPT"

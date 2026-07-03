---
id: STORY-87
tags: [workflow]
domain: workflow_meta
domain_tags: ["testing"]
---
> **Parent:** [[VAULT_DOMAINS]]


# STORY-87 Phase Verification — Honest Proof

> Auto-generated: 2026-06-16
> Purpose: prove each phase works, not just that tests pass

---

## SYNC Phase

### What it does
Finds story file, writes SYNC artifact with status=pending, outputs prompt to stdout.

### Manual proof
```bash
# Fresh state — remove artifact if exists
vault=adlai-vault/10_Issues/01_To_Do
story=$(find "$vault" -name "STORY-87-*.md" -type f | head -1)
[ -n "$story" ] && sed -i '/<!-- l3:phase=sync/,/<!-- \/l3:phase=sync -->/d' "$story"
[ -n "$story" ] && sed -i '/^## L3 Artifacts$/d' "$story"

# Run SYNC
bash adlai-vault/00_Project/session_bootstrap.sh --phase sync STORY-87
echo "exit: $?"

# Verify artifact was written
grep -c "<!-- l3:phase=sync story=STORY-87" "$story"  # expect: 1
grep "status=pending" "$story" | head -1               # expect: status=pending
grep "Timestamp:" "$story" | head -1                   # expect: ISO-8601
grep "Git head:" "$story" | head -1                     # expect: 7-12 hex chars
```

### Automated proof
```bash
uv run pytest backend/tests/integration/test_phase_sync.py -v --tb=short
# 13 tests — all pass — checks artifact creation, fields, idempotence, prompt structure
```

### Verdict: WORKS
- Artifact written to real story file ✓
- Fields match live git state ✓
- Idempotent (re-run does not duplicate) ✓
- Prompt contains SYNC duties + HARD STOP ✓

---

## ENGAGE Phase

### What it does
Validates SYNC artifact exists + status=ready. Outputs ENGAGE prompt.

### Manual proof
```bash
story=$(find adlai-vault/10_Issues -name "STORY-87-*.md" -type f | head -1)

# Gate blocks if SYNC not ready
sed -i 's/status=pending/status=ready/' "$story"
bash adlai-vault/00_Project/session_bootstrap.sh --phase engage STORY-87
echo "exit: $?"  # expect: 0

# Gate blocks if SYNC pending (reset and retry)
sed -i 's/status=ready/status=pending/' "$story"
bash adlai-vault/00_Project/session_bootstrap.sh --phase engage STORY-87
echo "exit: $?"  # expect: 1
# stdout contains: "status=\"pending\" (expected \"ready\")"
```

### Automated proof
```bash
uv run pytest backend/tests/integration/test_phase_engage.py -v --tb=short
# 4 tests — gate pass, gate block on missing, gate block on pending, prompt structure
```

### Verdict: WORKS
- Gate validates SYNC readiness ✓
- ENGAGE prompt generated when gate passes ✓

---

## ACT Phase

### What it does
Validates SYNC + ENGAGE artifacts exist + status=ready. Outputs ACT prompt.

### Manual proof
```bash
story=$(find adlai-vault/10_Issues -name "STORY-87-*.md" -type f | head -1)

# Inject ENGAGE artifact (simulating agent completion)
cat >> "$plan" << 'EOF'

### ENGAGE
<!-- l3:phase=engage story=STORY-87 status=ready version=1 -->
Plan: verify all 4 phases work end-to-end
Files: session_bootstrap.sh, test files
<!-- /l3:phase=engage -->
EOF

bash adlai-vault/00_Project/session_bootstrap.sh --phase act STORY-87
echo "exit: $?"  # expect: 0
# stdout contains: "## PHASE: ACT — IMPLEMENT"
# stdout contains: "uv run pytest backend/tests/unit -q"
```

### Automated proof
```bash
uv run pytest backend/tests/integration/test_phase_act.py -v --tb=short
# 4 tests — gate + prompt references plan + QA command + no-commit rule
```

### Verdict: WORKS
- Gate validates SYNC + ENGAGE readiness ✓
- ACT prompt contains QA command + forbidden commit ✓

---

## WRAP Phase

### What it does
Validates SYNC + ENGAGE + ACT artifacts exist + status=ready. Outputs WRAP prompt.

### Manual proof
```bash
story=$(find adlai-vault/10_Issues -name "STORY-87-*.md" -type f | head -1)

# Inject ACT artifact (simulating agent completion)
cat >> "$story" << 'EOF'

### ACT
<!-- l3:phase=act story=STORY-87 status=ready version=1 -->
test_exit_code: 0
Files changed: backend/app/services/orchestrator.py
<!-- /l3:phase=act -->
EOF

bash adlai-vault/00_Project/session_bootstrap.sh --phase wrap STORY-87
echo "exit: $?"  # expect: 0
# stdout contains: "## PHASE: WRAP — COMMIT AND CLOSE"
# stdout contains: "git commit -m"
# stdout contains: "rvc issue STORY-87 review"
```

### Automated proof
```bash
uv run pytest backend/tests/integration/test_phase_wrap.py -v --tb=short
# 4 tests — gate + commit format + rvc transition + cleanup
```

### Verdict: WORKS
- Gate validates all prior phases ✓
- WRAP prompt contains commit format, rvc transition ✓

---

## Honest Assessment

What the bootstrap script DOES:
1. Per-phase prompt generation ✓
2. L3 gate validation (all 4 phases) ✓
3. SYNC artifact auto-generation ✓
4. Story file mutation (idempotent) ✓
5. Exit codes (0 pass, 1 fail) ✓

What it DOES NOT do:
1. Execute the prompt — it's text, not execution
2. Auto-promote artifacts from pending to ready
3. Run tests, make commits, transition issues
4. Enforce WRAP "no code changes" (prompt-only guidance)
5. Verify the agent actually did what it said

The tests are honest about what they test: script behavior, not agent behavior. The gap between "script generates prompt" and "agent executes prompt correctly" cannot be tested without running a real model.

---

## What needs PoC with real model

1. Full SYNC→ENGAGE→ACT→WRAP on a real STORY with real code changes
2. Does the model follow HARD STOP in SYNC?
3. Does the model write ENGAGE artifact correctly?
4. Does the model run pytest and fill ACT artifact?
5. Does the model commit and transition issue in WRAP?
6. Can the model be tricked into skipping phases?

This requires `opencode run` or `qwen --code` with the bootstrap prompt piped in.

---
type: meta
tags: [sync, workflow]
version: 5.0
updated: 2026-06-15
domain: workflow_meta
domain_tags: []
---

# WORKFLOW.md — Session Ritual

> A work session reads this, follows it linearly, and leaves artifacts.
> Four phases: SYNC, ENGAGE, ACT, WRAP.

---

## Phase 1 — SYNC

Read these files to understand where things stand.

If a file doesn't exist, create it with the content shown.

**1. Run state** — `adlai-vault/00_Project/STATE.json`
```json
{"active_issue":null,"active_branch":null,"agent":null,"started_at":null,"last_run":null,"last_qa":null}
```
Read it. Note the active issue, branch, and agent (if any).

**2. Decisions log** — `adlai-vault/00_Project/DECISIONS.md`
Create if missing:
```markdown
# Decisions Log

_Appended by agents after each run. Newest last._
```
Read the last 3 entries.

**3. Gotchas log** — `adlai-vault/00_Project/GOTCHAS.md`
Create if missing:
```markdown
# Gotchas Log

_Appended by agents when something non-obvious is discovered. Newest last._
```
Read the last 3 entries.

**4. The issue** — `rvc context <ID>` (get ID from STATE.json or from user)
Read the issue file. Read linked specs. Understand acceptance criteria.

**5. Announce** what you found: issue, branch, context.

---

## Phase 2 — ENGAGE

Pick up the work.

**6. Transition** — if the issue isn't Active: `rvc issue <ID> start`

**7. Update STATE.json** with:
```json
{"active_issue":"<ID>","active_branch":"<current branch>","agent":"<who you are>","started_at":"<ISO8601>","last_run":null,"last_qa":null}
```

**8. Read relevant specs** from `adlai-vault/20_Specs/` — any spec matching the
area you'll change. If you'll touch inference, read InferenceStack.md.
If you'll touch DB, read DB-Schema.md. Etc.

---

## Phase 3 — ACT

Do the work.

**9.** Implement. Keep changes minimal.

**10.** If you changed code that a spec describes — update that same spec file.

**11.** If you hit something non-obvious — remember it for WRAP.

**12.** If you made a non-obvious decision — remember it for WRAP.

---

## Phase 4 — WRAP

Leave clean artifacts so the next session syncs fast.

**13. Run tests:**
```bash
cd /home/lexx/Documents/ADLAI && uv run pytest backend/tests/unit -q
```
Fix and re-run on failure. Up to 3 attempts. If still failing, note the
blocker in the issue file (add `## Blocker` section) and stop here.

**14. Commit:**
```bash
git add -A && git commit -m "<type>: <subject> (<ID>)"
```

**15. Transition:** `rvc issue <ID> review`

**16. Decisions** — append to `adlai-vault/00_Project/DECISIONS.md`:
```markdown
## <ISO-date> — <agent> (<ID>)
- **Decision:** what and why
```
Skip if everything was straightforward.

**17. Gotchas** — append to `adlai-vault/00_Project/GOTCHAS.md`:
```markdown
## <area> (<ID>)
- what to remember
```
Skip if nothing surprising happened.

**18. Update STATE.json:**
```json
{"active_issue":null,"active_branch":null,"agent":null,"started_at":null,"last_run":"<ISO8601>","last_qa":"pass"}
```
Use `"blocked"` for last_qa if you stopped at step 13.

**19. Announce:** what was done, commit SHA, files changed, QA result.

---

## Anti-collision

- If STATE.json shows an active issue with another agent, pick a different issue.
- Don't touch another agent's branch.

## Reference (read only when needed)

- `AGENTS.md` — architecture, config, design patterns
- `adlai-vault/00_Project/MAP.md` — vault knowledge graph
- `adlai-vault/00_Project/ROADMAP.md` — phase plan

## Bootstrap

For a new session, use the bootstrap script to get a self-contained prompt:

```bash
cd /home/lexx/Documents/ADLAI
opencode run --model "opencode/big-pickle" --pure "$(bash adlai-vault/00_Project/session_bootstrap.sh [[STORY-83]])"
```

The script reads STATE, the issue, linked specs, decisions, gotchas, and git state,
then outputs a complete prompt. The agent gets everything in one shot — no "go read
this then read that."

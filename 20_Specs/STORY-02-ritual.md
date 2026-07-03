---
tags: [spec]
---
> **Parent:** [[VAULT_DOMAINS]]

---
domain: workflow_meta
domain_tags: []

# STORY-02 Automated Execution Ritual

## Where Artifacts Live

All artifacts stay inside RVC vault folders (numeric prefix). No extra directories.

| Artifact | Vault Location |
|----------|---------------|
| RunState ledger | `90_Assets/story-02-runstate.md` |
| Story specs | `10_Issues/01_To_Do/` |
| Epic & child stories | `conductor/stories/` (source of truth until RVC migration) |
| Session outputs | `90_Assets/story-02-artifacts/` (created on first `finish`) |

## First Run: Initialize RunState

```bash
cd conductor
python -c "
from pathlib import Path
from datetime import datetime, timezone

now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
template = '''# STORY-02 Epic RunState Ledger

## Epic Metadata
- Started: {now}
- Current Phase: 1
- Last Updated: {now}

## State Keys

| Key | Value | Set By | Status |
|-----|-------|--------|--------|
| story_research_ctx | \"\" | STORY-002 | pending |
| story_text | \"\" | STORY-003 | pending |
| story_retries | 0 | STORY-004 | pending |
| story_finalized | false | STORY-004 | pending |
| story_review_feedback | \"\" | STORY-004 | pending |
| rvc_story_id | \"\" | STORY-005 | pending |
| contract_proposal | \"\" | STORY-006 | pending |
| contract_valid | false | STORY-007 | pending |
| status | init | -- | -- |

## Story Completion Tracker

| Story | Phase | Status | Finished At |
|-------|-------|--------|-------------|
| STORY-001 | 1 | pending | - |
| STORY-008 | 1 | pending | - |
| STORY-002 | 2 | pending | - |
| STORY-003 | 2 | pending | - |
| STORY-004 | 2 | pending | - |
| STORY-005 | 3 | pending | - |
| STORY-006 | 3 | pending | - |
| STORY-007 | 3 | pending | - |
| STORY-009 | 3 | pending | - |

## History Log
- [{now}] RunState initialized
'''
path = Path('../90_Assets/story-02-runstate.md')
path.write_text(template.format(now=now))
print(f'RunState created: {path}')
"
```

Or simply copy the template from `../90_Assets/story-02-runstate.md` if it already exists.

## Start a Session: Pre-Flight Automation

Run this before opening an agentic session. It checks dependencies and prints the context you must load.

```bash
cd conductor
python -c "
import sys
from pathlib import Path

story = sys.argv[1].upper()
STORY_META = {
    'STORY-001': {'deps': [], 'files': ['pipeline.py'], 'phase': 1},
    'STORY-008': {'deps': [], 'files': ['projects_config.py', 'projects/adlai.toml'], 'phase': 1},
    'STORY-002': {'deps': ['STORY-001', 'STORY-008'], 'files': ['pipeline.py'], 'phase': 2},
    'STORY-003': {'deps': ['STORY-001', 'STORY-002'], 'files': ['pipeline.py'], 'phase': 2},
    'STORY-004': {'deps': ['STORY-001', 'STORY-003'], 'files': ['pipeline.py'], 'phase': 2},
    'STORY-005': {'deps': ['STORY-001', 'STORY-004'], 'files': ['pipeline.py'], 'phase': 3},
    'STORY-006': {'deps': ['STORY-001', 'STORY-005'], 'files': ['pipeline.py'], 'phase': 3},
    'STORY-007': {'deps': ['STORY-001', 'STORY-006'], 'files': ['pipeline.py'], 'phase': 3},
    'STORY-009': {'deps': ['STORY-001','STORY-002','STORY-003','STORY-004','STORY-005','STORY-006','STORY-007','STORY-008'], 'files': ['pipeline.py'], 'phase': 3},
}

if story not in STORY_META:
    print(f'Unknown story: {story}'); sys.exit(1)

meta = STORY_META[story]
print(f'\\n=== PRE-FLIGHT: {story} ===\\n')

# Parse runstate
state = {}
runstate_path = Path('../90_Assets/story-02-runstate.md')
if runstate_path.exists():
    text = runstate_path.read_text()
    in_tracker = False
    for line in text.splitlines():
        if 'Story Completion Tracker' in line:
            in_tracker = True; continue
        if in_tracker and line.startswith('|') and 'Story' not in line and '---' not in line:
            parts = [p.strip() for p in line.strip('|').split('|')]
            if len(parts) >= 3:
                state[parts[0]] = parts[2]

blocked = [d for d in meta['deps'] if state.get(d, 'pending') != 'done']
if blocked:
    print(f'[BLOCKED] Needs: {blocked}'); sys.exit(1)

print('[deps] All satisfied.')
print(f'[context] Read these files: {meta[\"files\"]}')
print(f'[context] Read story spec: stories/{story.lower().replace(\"-\", \"-\")}*.md')
print(f'[context] Current phase: {meta[\"phase\"]}')
print('\\n[ready] Open agentic session now.')
print(f'[next] After session: update runstate tracker, set {story} = done')
" STORY-001
```

## End a Session: Post-Flight Automation

After the agentic session finishes, update the RunState. This is the "artifact collection" step.

```bash
cd conductor
python -c "
import sys, re
from pathlib import Path
from datetime import datetime, timezone

story = sys.argv[1].upper()
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
path = Path('../90_Assets/story-02-runstate.md')
text = path.read_text()

# Update story status in tracker table
lines = text.splitlines()
new_lines = []
for line in lines:
    if line.startswith(f'| {story} '):
        parts = [p.strip() for p in line.strip('|').split('|')]
        parts[2] = 'done'
        parts[3] = now
        new_lines.append(f'| {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} |')
    else:
        new_lines.append(line)

# Append history
new_lines.append(f'- [{now}] {story} finished')

# Update Last Updated
for i, line in enumerate(new_lines):
    if line.startswith('- Last Updated:'):
        new_lines[i] = f'- Last Updated: {now}'

path.write_text('\\n'.join(new_lines) + '\\n')
print(f'[done] {story} marked done in RunState.')
print(f'[artifact] If you generated outputs, save them to ../90_Assets/story-02-artifacts/{story}/')
" STORY-001
```

## Story-Specific State Keys to Update Manually

Some stories produce values that other stories consume. After `finish`, paste these into the **State Keys** table in `../90_Assets/story-02-runstate.md`.

| Story | Key | What to paste |
|-------|-----|---------------|
| STORY-002 | `story_research_ctx` | Research summary output |
| STORY-003 | `story_text` | Generated narrative story |
| STORY-004 | `story_finalized`, `story_retries`, `story_review_feedback` | true/false, count, feedback |
| STORY-005 | `rvc_story_id` | RVC issue ID (e.g. STORY-91) |
| STORY-006 | `contract_proposal` | Generated contract text |
| STORY-007 | `contract_valid` | true/false |
| STORY-009 | `status` | New pipeline status |

## Session Checklist (Copy into each session)

```markdown
## Session: <STORY-XXX>

### Pre-Flight
- [ ] Run pre-flight script (dependency check + context list)
- [ ] Read story spec file
- [ ] Read all dependency outputs from RunState
- [ ] Read referenced source files
- [ ] Confirm no STORY-01 blocker

### Execution
- [ ] Open agentic session with correct mode (code/architect)
- [ ] Implement acceptance criteria
- [ ] Run smoke tests / verification

### Post-Flight
- [ ] Run finish script (mark story done, append history)
- [ ] Update State Keys table with new outputs
- [ ] Save generated artifacts to `../90_Assets/story-02-artifacts/<STORY-XXX>/`
- [ ] Write handoff note for next story
```

## Mapping to Future Pipeline

| Manual Ritual Step | Automated Pipeline Equivalent |
|-------------------|------------------------------|
| `init` | `RunState` initialized at graph entry |
| Pre-flight script | Node receives `state` dict, checks deps via graph edges |
| Post-flight script | Node returns `state` updates, LangGraph checkpoints |
| State Keys table | `RunState` TypedDict fields |
| History Log | `_log()` events appended per node |
| `../90_Assets/story-02-artifacts/` | `_save_raw_stdout()` + `_save_prompt()` |

## Execution Order

```
Phase 1 (parallel):  STORY-001 + STORY-008
Phase 2 (sequential): STORY-002 -> STORY-003 -> STORY-004
Phase 3 (sequential): STORY-005 -> STORY-006 -> STORY-007 -> STORY-009
```

**Circular dependency resolution:** Write all node functions in Phase 2-3 first, then wire them in STORY-009 last.


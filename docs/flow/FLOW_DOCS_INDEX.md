---
domain: workflow_meta
domain_tags: []

# Flow Documentation Index

*This directory contains all flow/orchestration-related documentation consolidated from the ADLAI project vault. These files conceptually belong to the Conductor+RVC meta-project, not ADLAI's legal AI business logic.*

---

## Directory Structure

```
docs/flow/
├── stories/        # Epics and stories tracking the workflow evolution
├── specs/          # Architecture specs and design documents
├── meta/           # Checkpoints, postmortems, and status docs
└── scripts/        # Reference copies of bootstrap scripts
```

---

## Stories

| File | ID | Title | Status |
|------|-----|-------|--------|
| `EPIC-15.md` | EPIC-15 | Workflow Orchestration & Pult Integration | To Do |
| `STORY-87.md` | STORY-87 | Workflow Layered Architecture (Active) | Active |
| `STORY-87-backlog.md` | STORY-87 | Earlier backlog version | Backlog |
| `STORY-87-verification.md` | STORY-87 | Verification notes | To Do |
| `STORY-92.md` | STORY-92 | L3 MVP-1: SYNC-only phase prompt | Done |
| `STORY-93.md` | STORY-93 | L3 MVP-2: SYNC artifact + ENGAGE gate | Done |
| `STORY-94.md` | STORY-94 | Core Path Resolution (`paths.py`) | To Do |
| `STORY-95.md` | STORY-95 | Pult Phase 1: Python Wrapper & Error Classifier | To Do |
| `STORY-96.md` | STORY-96 | Pult Phase 2: Structured Artifact Injection | To Do |
| `STORY-97.md` | STORY-97 | Fix ACT/WRAP Prompt Gates | To Do |
| `STORY-98.md` | STORY-98 | Real-Vault Integration Testing | To Do |
| `STORY-99.md` | STORY-99 | Pult Phase 3: Absorption (Deprecate Bash) | To Do |

---

## Specs

| File | Purpose |
|------|---------|
| `WORKFLOW.md` | The 4-phase session ritual (SYNC → ENGAGE → ACT → WRAP) |
| `WORKFLOW_PULT.md` | Pult architecture, error classification, implementation strategy |
| `WORKFLOW_LAYERS.md` | OSI-style 6-layer enforcement model |
| `WORKFLOW_DOMAIN.md` | Domain root node — entry point for workflow sub-derivatives |

---

## Meta

| File | Purpose |
|------|---------|
| `CHECKPOINT.md` | STORY-87 test checkpoint — 103 tests pass but on temp vault |
| `CHECKPOINT_POSTMORTEM.md` | 6 systemic fragilities identified (Russian/English) |

---

## Scripts

| File | Purpose |
|------|---------|
| `session_bootstrap.sh` | L5 bootstrap script (436 lines) — generates phase-specific prompts |

---

## Original Locations

These files were copied from `~/Documents/ADLAI/adlai-vault/` on 2026-06-28.

- Stories: `10_Issues/{00_Backlog,01_To_Do,02_Active,03_Review,04_Done}/`
- Specs: `20_Specs/`
- Meta: `00_Project/`
- Scripts: `00_Project/`

The originals remain in ADLAI vault for backward compatibility. These copies are the canonical reference for cross-system planning.



## Sub-Documents & Context
- [[CHECKPOINT]]
- [[CHECKPOINT_POSTMORTEM]]

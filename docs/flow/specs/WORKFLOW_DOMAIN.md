---
type: domain
tags: "[cicd, domain-root, entry-point, eval, frontend, llm, meta, retrieval, testing, workflow]"
version: 1.0
created: 2026-06-15
---

# Workflow Domain — Root Node

> This is the entry point for the Workflow Engine domain. When diving into
> workflow sub-derivatives, start here. Return here to re-anchor. Do not mix
> ADLAI legal context with workflow meta context.

---

## Domain Boundaries

```
┌─────────────────────────────────────────┐
│ WORKFLOW DOMAIN (meta-project)          │
│                                         │
│  ~/Q/conductor          L4 outer ring   │
│  ~/Q/vault-protocol     L2 artifacts    │
│  session_bootstrap.sh   L5 bootstrap    │
│  qwen CLI               L0 tooling      │
│  opencode CLI           L0 tooling      │
│                                         │
│  ─ ─ ─ INTEGRATION ─ ─ ─              │
│  adlai-vault/20_Specs/                  │
│    WORKFLOW_LAYERS.md                   │
│    WORKFLOW.md                          │
│    WORKFLOW_DOMAIN.md  ← you are here   │
│  adlai-vault/00_Project/                │
│    session_bootstrap.sh                 │
│    STATE.json / DECISIONS / GOTCHAS     │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ ADLAI DOMAIN (target project)           │
│                                         │
│  ~/Documents/ADLAI/  legal AI           │
│  backend/             RAG pipeline      │
│  frontend/            Vue 3 SPA         │
│  adlai-vault/         legal knowledge   │
│    [[STORY-01]]..[[STORY-85]]                   │
└─────────────────────────────────────────┘
```

---

## Core Model

[[WORKFLOW_LAYERS]] — the OSI enforcement model. Six layers. Each layer
constrains the one below. The critical gap is Layer 3 (Phase Gating).

---

## Sub-Derivatives

| Branch | File |
|---|---|
| OSI Model | [[WORKFLOW_LAYERS]] |
| Session Ritual | [[WORKFLOW]] |
| Bootstrap Script | `session_bootstrap.sh` |
| Qwen CLI | `qwen` tooling |
| OpenCode CLI | `opencode` tooling |
| Conductor | `~/Q/conductor` |
| Vault Protocol | `~/Q/vault-protocol` |
| Phase Gating | [[L3_PHASE_GATING]] (SYNC→ENGAGE built) |
| Integration Test Epic | [[EPIC_WORKFLOW_INTEGRATION_TESTS]] |

---

## Active Stories

- [[STORY-87]] — Workflow Layered Architecture (L3 phase gating design)
- [[STORY-86]] — MAPPING_RETRIEVAL.md spec fixes
- [[STORY-88]] — STALE-PICKLE-FIX integration test

---

## Quick Context

When a new workflow session starts, the agent reads:
1. [[WORKFLOW_LAYERS]] — understand the architecture
2. [[WORKFLOW]] — understand the ritual
3. `STATE.json` — understand current state
4. `DECISIONS.md` — what was decided
5. `GOTCHAS.md` — what to avoid

When diving into a sub-derivative, come back here to re-anchor.
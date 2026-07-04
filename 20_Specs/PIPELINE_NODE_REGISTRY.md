---
type: architecture
domain: workflow_meta
status: draft
tags: [pipeline, conductor, node-registry]
created: 2026-07-04
related:
  - "[[RECOMMENDATIONS]]"
  - "[[WORKFLOW_PULT]]"
  - "[[STORY-01 - Research Task — Prompt Generation & Enrichment Architecture]]"
  - "[[EPIC-003-Storywriter-Contract-Pipeline]]"
  - "[[0.0.0_ASSEMBLY]]"
  - "[[EPIC-1-RVC-REVIVAL-WITH-FLOW]]"
  - "[[EPIC-002-Conductor-v0.2-Hardening]]"
---

# Pipeline Node Registry

Single source of truth mapping every defined conductor node to its pipeline position, routing key, and connection status.

![[Dry-Run Output Sample]]
Another [[dry-run sample as a whole piece]]
## Node Map

| Node | Routing Key | Pipeline Position | Status | Connected To | Notes |
|------|-------------|-------------------|--------|--------------|-------|
| Plan | `plan` | `plan_node` | ✅ Active | `act`, `plan_reviser` | Core node |
| Act | `act` | `act_node` | ✅ Active | `qa`, `after_approve` | Core node |
| QA | `qa` | `qa_node` | ✅ Active | `plan_reviser`, `after_approve` | Core node |
| PlanReviser | `plan_reviser` | `plan_reviser_node` | ⚠️ Stub | `plan` | Documented stub — needs real diagnosis |
| Bulk | `bulk` | — | ❌ Unwired | — | Defined in TOML, no pipeline edge |
| Pult | — | — | ❌ Orphaned | — | Defined in [[WORKFLOW_PULT]], not wired into conductor pipeline |
| Prompt Builder | — | — | ❌ Orphaned | — | Research task [[STORY-01 - Research Task — Prompt Generation & Enrichment Architecture]] with 3 analysis nodes |

## Orphaned Node Details

### Bulk Node
- **Routing Key**: `bulk`
- **Status**: ❌ Unwired
- **Problem**: Defined in `adlai.toml` routing table but no pipeline edge routes to it
- **Fix**: Wire it up for high-volume mechanical refactors, or drop the routing key

### PlanReviser
- **Routing Key**: `plan_reviser`
- **Pipeline Position**: `plan_reviser_node`
- **Status**: ⚠️ Stub
- **Problem**: Documented stub — does not actually diagnose failures
- **Fix**: Replace with real diagnosis loop (see [[RECOMMENDATIONS]] Priority 2)

### Pult
- **Routing Key**: None
- **Pipeline Position**: None
- **Status**: ❌ Orphaned
- **Problem**: Fully specified in [[WORKFLOW_PULT]] with phased implementation plan, but no pipeline edge, no routing key, no integration point in the conductor graph
- **Fix**: Add `pult` routing key to TOML, create `pult_node` in pipeline, wire as L5 entry point

### Prompt Builder (STORY-01 cluster)
- **Routing Key**: None
- **Pipeline Position**: None
- **Status**: ❌ Orphaned
- **Problem**: Research task [[STORY-01 - Research Task — Prompt Generation & Enrichment Architecture]] with 3 analysis nodes ([[Analysis Nemotron]], [[Analysis Grok]], [[Analysis GPT]]) — no parent epic, no pipeline position
- **Fix**: Link to [[EPIC-003-Storywriter-Contract-Pipeline]] as prerequisite dependency; create `prompt_builder` service as cross-cutting concern

## Connection Map

```
EPIC-003-Storywriter-Contract-Pipeline
├── STORY-01 (prerequisite research)
│   ├── Analysis Nemotron
│   ├── Analysis Grok
│   └── Analysis GPT
│   └── → Prompt Builder (cross-cutting service)
├── Bulk Node (unwired)
├── PlanReviser (stub)
└── Pult (orphaned)

RECOMMENDATIONS
├── Priority 2 → PlanReviser fix
├── Priority 6 → Prompt Builder (informed by STORY-01)
└── Priority 5 → Bulk Node (wire or drop)

WORKFLOW_PULT
└── Pult → L5 entry point (needs routing key + pipeline node)
```

## Action Items

1. **Link [[STORY-01 - Research Task — Prompt Generation & Enrichment Architecture]]** to [[EPIC-003-Storywriter-Contract-Pipeline]] as prerequisite dependency
2. **Add `pult` routing key** to TOML routing table
3. **Create `pult_node`** in conductor pipeline
4. **Wire Bulk node** or drop its routing key
5. **Replace PlanReviser stub** with real diagnosis loop

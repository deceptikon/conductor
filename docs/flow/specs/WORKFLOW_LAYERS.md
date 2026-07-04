---
type: spec
tags: [architecture, workflow]
version: 1.0
created: 2026-06-15
updated: 2026-06-15
domain: meta
---

# WORKFLOW LAYERS — OSI Enforcement Model

> The workflow is not a document. It is a stack of layers, each enforcing the
> one below it. A layer cannot be skipped because the layer below never receives
> the data to skip it.

---

## The Model

```
┌──────────────────────────────────────────────────┐
│ LAYER 5 — Bootstrap                               │
│   session_bootstrap.sh                            │
│   "Assemble everything the agent needs. Deliver   │
│    once."                                         │
│   Protocol: context payload → Layer 4             │
├──────────────────────────────────────────────────┤
│ LAYER 4 — Conductor (outer enforcement ring)      │
│   Plan → Approve → Act → QA → Commit              │
│   Hard LangGraph nodes, checkpointed, human       │
│   interrupt at Approve. Stateless workers.        │
│   Protocol: node_name + state → Layer 3           │
├──────────────────────────────────────────────────┤
│ LAYER 3 — Phase Gating (inner enforcement ring)   │
│   SYNC → ENGAGE → ACT → WRAP                      │
│   Each phase = one LLM invocation. One prompt.    │
│   Phase N output is Phase N+1 input. The LLM      │
│   cannot skip phases because it never sees them.  │
│   Protocol: phase + required_artifact → Layer 2   │
├──────────────────────────────────────────────────┤
│ LAYER 2 — Artifacts (handoff protocol)            │
│   STATE.json, DECISIONS.md, GOTCHAS.md            │
│   "What happened, what was decided, what to       │
│    avoid." Cross-session state lives here.        │
│   Protocol: read state → act → write state        │
├──────────────────────────────────────────────────┤
│ LAYER 1 — Tool Sandbox                            │
│   Permissions: read-only in SYNC, write in ACT,   │
│   no destructive ops ever.                        │
│   Protocol: phase → allowed_actions               │
├──────────────────────────────────────────────────┤
│ LAYER 0 — Model (substrate)                       │
│   The LLM itself. No control, only steering.      │
└──────────────────────────────────────────────────┘
```

---

## Interlayer Protocols

| From → To | What flows | How |
|---|---|---|
| L5 → L4 | Context payload | Bootstrap script output → conductor worker prompt |
| L4 → L3 | Pipeline node + state | Conductor feeds phase-specific prompt to agent |
| L3 → L2 | Phase completion artifact | SYNC → announcement, ENGAGE → state update, ACT → code, WRAP → commit |
| L2 → L1 | Current phase | Phase name determines allowed tools |
| L1 → L0 | Filtered tool set | Model receives scoped tool list |

---

## The Core Insight

A flat markdown document with 19 numbered steps across 4 phases is a
**suggestion** — the LLM can freely ignore any step.

**Test proof:** Both Big Pickle and Qwen3.6 read the workflow, acknowledged
it, then immediately blended phases (planning ACT implementation while
still in SYNC). The model was willing to follow the ritual, but the
single-invocation format physically prevents it from stopping at phase
boundaries.

**The fix:** Split the 4-phase ritual into 4 separate LLM invocations.
Each invocation gets a prompt that only describes its phase and ends with
a hard STOP boundary. The LLM cannot skip phases because it never sees them.

```
session_bootstrap.sh --phase sync STORY-NN    # SYNC → qwen, read-only tools
session_bootstrap.sh --phase engage STORY-NN   # ENGAGE → qwen, transition tools
session_bootstrap.sh --phase act STORY-NN      # ACT → qwen, write tools
session_bootstrap.sh --phase wrap STORY-NN     # WRAP → qwen, commit tools
```

Each invocation passes `--allowed-tools` scoped to its phase. Each prompt
ends with "STOP. Do not proceed." The next phase reads the prior phase's
output as context.

---

## Phase Enforcement Rules

| Phase | Allowed Tools | Required Artifact |
|---|---|---|
| SYNC | `read_file`, `search_files`, `rvc_*` (read) | `SYNC_ANNOUNCEMENT.md` |
| ENGAGE | `rvc_issue_start`, `write_file` (STATE only) | `STATE.json` updated |
| ACT | `write_file`, `edit`, `run_shell_command` | Tests pass (exit 0) |
| WRAP | `git`, `rvc_issue_review`, `write_file` (DECISIONS/GOTCHAS) | Commit SHA |

---

## Sub-derivatives

This model is a **root node** in the ADLAI knowledge graph. Related branches:

- [[STORY-87]] — detailed analysis of bottlenecks mapped to layers
- [[WORKFLOW]] — the 4-phase ritual (what the agent reads)
- `session_bootstrap.sh` — the L5 bootstrap implementation
- `~/X/TEAMFLOW/conductor` — the L4 LangGraph orchestration engine
- `~/X/TEAMFLOW/RVC` — the L2 artifact management CLI

When diving deeper into any sub-derivative, return here to re-anchor in the
full model. Do not mix contexts — each layer is a separate concern.
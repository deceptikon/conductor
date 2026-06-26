"""The LangGraph pipeline: Plan -> Review -> Human Gate -> Act -> QA -> PlanReviser -> Commit.

State is the durable run ledger, checkpointed to SQLite so any run is
resumable and time-travel debuggable. The human-approval gate uses
LangGraph's native `interrupt()` — the graph pauses, persists, and resumes
on a `Command(resume=...)` with the human's decision.

The QA node is the conditional heart: on failure it routes back to ACT
(feeding the failure log to the fixing worker) until max_qa_retries, then
routes to PLAN_REVISER so the plan itself can be corrected.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .projects_config import ProjectConfig
from .schema import Plan, TaskNode

logger = logging.getLogger("conductor.pipeline")


class RunState(TypedDict, total=False):
    # --- inputs ---
    project: str
    task: str                  # the user's task description
    task_type: str             # conventional-commit type: feat|fix|refactor|...
    issue_id: str              # RVC/vault issue id, e.g. STORY-83 (optional)
    # --- accumulated ledger ---
    contract: str              # AGENTS.md content injected into every worker
    plan: Plan | None          # structured plan output (replaces string plan)
    plan_locked: bool          # set by reviewer after validation
    approved: bool             # human gate result
    rejection_note: str        # if human rejects, why (fed back to planner)
    act_output: str            # latest ACT worker output
    qa_passed: bool
    qa_log: str                # latest QA stdout+stderr
    qa_attempts: int
    commit_sha: str
    status: str                # planning|reviewing|awaiting_approval|acting|qa|plan_revising|done|qa_failed|rejected
    history: list              # append-only event log for the ledger


def _read_contract(cfg: ProjectConfig) -> str:
    if cfg.agents_md.exists():
        return cfg.agents_md.read_text()
    return "(no AGENTS.md found — operate conservatively)"


def _log(state: RunState, event: str, **data) -> list:
    h = list(state.get("history", []))
    h.append({"event": event, **data})
    return h


def _git_context(repo: Path) -> str:
    """Collect lightweight git context for the planner."""
    ctx = []
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        ).stdout.strip()
        ctx.append(f"Branch: {branch}")
    except Exception:
        pass
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        ).stdout.strip()
        if log:
            ctx.append(f"Recent commits:\n{log}")
    except Exception:
        pass
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        ).stdout.strip()
        if status:
            ctx.append(f"Uncommitted changes:\n{status}")
    except Exception:
        pass
    return "\n".join(ctx)


def _rvc_context(issue_id: str, repo: Path) -> str:
    """Fetch RVC vault context for an issue via the rvc CLI.

    Falls back to ~/.local/bin/rvc if rvc is not on PATH.
    Returns empty string on failure so the pipeline never breaks.
    """
    if not issue_id:
        return ""
    rvc_bin = "rvc"
    # Verify rvc is on PATH; fall back to ~/.local/bin/rvc
    if subprocess.run(["which", rvc_bin], capture_output=True).returncode != 0:
        fallback = Path.home() / ".local" / "bin" / "rvc"
        if fallback.exists():
            rvc_bin = str(fallback)
        else:
            logger.warning("[rvc] binary not found on PATH or at %s", fallback)
            return ""
    try:
        proc = subprocess.run(
            [rvc_bin, "context", issue_id],
            cwd=str(repo), capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            logger.info("[rvc] fetched context for %s (%d chars)", issue_id, len(proc.stdout))
            return f"# RVC ISSUE CONTEXT ({issue_id})\n{proc.stdout.strip()}\n"
        else:
            logger.warning("[rvc] context fetch failed for %s: %s", issue_id, proc.stderr.strip()[:200])
    except Exception as e:
        logger.warning("[rvc] exception fetching context for %s: %s", issue_id, e)
    return ""


def _plan_to_json(plan: Plan | None) -> str:
    """Serialize a Plan to JSON string for prompts / human gate."""
    if plan is None:
        return "{}"
    return json.dumps(
        {
            "id": plan.id,
            "version": plan.version,
            "nodes": [
                {
                    "id": n.id,
                    "description": n.description,
                    "dependencies": n.dependencies,
                    "expected_output": n.expected_output,
                    "test_case": n.test_case,
                    "artifact_path": n.artifact_path,
                }
                for n in plan.nodes
            ],
            "topo_order": plan.topo_order,
        },
        indent=2,
    )


def _json_to_plan(data: dict) -> Plan:
    """Deserialize a Plan from JSON dict."""
    nodes = []
    for n in data.get("nodes", []):
        nodes.append(
            TaskNode(
                id=n["id"],
                description=n.get("description", ""),
                dependencies=n.get("dependencies", []),
                expected_output=n.get("expected_output", ""),
                test_case=n.get("test_case", ""),
                artifact_path=n.get("artifact_path"),
            )
        )
    return Plan(
        id=data.get("id", "plan"),
        version=data.get("version", 1),
        nodes=nodes,
        topo_order=data.get("topo_order", []),
    )


def build_graph(cfg: ProjectConfig):
    """Compile the pipeline for a given project config."""

    def plan_node(state: RunState) -> RunState:
        logger.info("[plan] starting plan generation")
        contract = _read_contract(cfg)
        worker = cfg.worker_for("plan")
        rej = state.get("rejection_note", "")
        git_ctx = _git_context(cfg.repo)
        issue_ctx = _rvc_context(state.get("issue_id", ""), cfg.repo)
        prompt = (
            f"{contract}\n\n"
            f"# REPOSITORY CONTEXT\n{git_ctx}\n\n"
            + (issue_ctx + "\n" if issue_ctx else "")
            + f"# TASK TO PLAN\n{state['task']}\n\n"
            + (f"# PRIOR PLAN WAS REJECTED — address this feedback:\n{rej}\n\n" if rej else "")
            + "Produce a concrete implementation plan as JSON conforming to this schema:\n"
            "{\n"
            '  "id": "string",\n'
            '  "version": 1,\n'
            '  "nodes": [\n'
            '    {\n'
            '      "id": "string",\n'
            '      "description": "string",\n'
            '      "dependencies": ["other_node_id"],\n'
            '      "expected_output": "string (contract for coder)",\n'
            '      "test_case": "string (contract for QA runner)",\n'
            '      "artifact_path": "optional/path"\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "Rules:\n"
            "- The plan must be a DAG (no cycles).\n"
            "- Every dependency must reference a node id that exists in the plan.\n"
            "- Every node must have non-empty expected_output and test_case.\n"
            "- Do NOT write code or modify files — planning only.\n"
        )
        logger.debug("[plan] prompt length=%d", len(prompt))
        res = worker.run(prompt, cwd=cfg.repo, timeout=600)
        plan: Plan | None = None
        parse_ok = False
        try:
            text = res.text.strip()
            # Handle markdown code fences
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            data = json.loads(text)
            plan = _json_to_plan(data)
            parse_ok = True
            logger.info("[plan] parsed plan with %d nodes", len(plan.nodes))
        except Exception as e:
            logger.warning("[plan] failed to parse planner output: %s", e)

        return {
            "contract": contract,
            "plan": plan,
            "plan_locked": False,
            "status": "reviewing",
            "history": _log(state, "plan",
                            worker=res.worker, ok=res.ok, cmd=res.cmd,
                            parse_ok=parse_ok),
        }

    def reviewer_node(state: RunState) -> RunState:
        logger.info("[review] validating plan")
        plan = state.get("plan")
        if plan is None:
            logger.warning("[review] reject: planner output was not valid JSON")
            return {
                "status": "planning",
                "rejection_note": "Planner output was not valid JSON or did not match the Plan schema. Please emit valid JSON.",
                "history": _log(state, "reviewer_reject", reason="parse_failed"),
            }
        errors = plan.validate()
        if errors:
            logger.warning("[review] reject: %d validation errors", len(errors))
            return {
                "status": "planning",
                "rejection_note": "Plan validation failed:\n" + "\n".join(f"- {e}" for e in errors),
                "history": _log(state, "reviewer_reject", errors=errors),
            }
        # Valid plan: compute topo_order and lock it
        plan.topo_order = plan.compute_topo_order()
        logger.info("[review] plan locked, topo_order=%s", plan.topo_order)
        return {
            "plan": plan,
            "plan_locked": True,
            "status": "awaiting_approval",
            "history": _log(state, "reviewer_lock",
                            nodes=len(plan.nodes),
                            topo_order=plan.topo_order),
        }

    def approve_node(state: RunState) -> RunState:
        plan_json = _plan_to_json(state.get("plan"))
        logger.info("[approve] waiting for human decision")
        decision = interrupt({
            "type": "approval_request",
            "plan": plan_json,
            "task": state.get("task", ""),
            "note": "Respond with {'approved': true} to accept, {'approved': false, 'note': '...'} to reject, or {'edited_plan': <Plan JSON>} to edit and resubmit.",
        })
        if isinstance(decision, dict):
            approved = bool(decision.get("approved"))
            note = decision.get("note", "")
            edited = decision.get("edited_plan")
            if edited is not None:
                # Human edited the plan — route back to reviewer
                try:
                    if isinstance(edited, str):
                        edited = json.loads(edited)
                    new_plan = _json_to_plan(edited)
                    logger.info("[approve] human submitted edited plan with %d nodes", len(new_plan.nodes))
                    return {
                        "plan": new_plan,
                        "plan_locked": False,
                        "status": "reviewing",
                        "history": _log(state, "human_edit"),
                    }
                except Exception as e:
                    logger.warning("[approve] human edit was invalid: %s", e)
                    # Edit was invalid JSON — treat as rejection with note
                    return {
                        "approved": False,
                        "rejection_note": f"Edited plan was invalid: {e}",
                        "status": "rejected",
                        "history": _log(state, "human_edit_reject", error=str(e)),
                    }
            if approved:
                logger.info("[approve] approved by human")
                return {"approved": True, "status": "acting",
                        "history": _log(state, "approved")}
            logger.info("[approve] rejected by human: %s", note)
            return {"approved": False, "rejection_note": note, "status": "rejected",
                    "history": _log(state, "rejected", note=note)}
        # Fallback: treat truthy as approve, falsy as reject
        if decision:
            logger.info("[approve] approved (fallback)")
            return {"approved": True, "status": "acting",
                    "history": _log(state, "approved")}
        logger.info("[approve] rejected (fallback)")
        return {"approved": False, "status": "rejected",
                "history": _log(state, "rejected")}

    def act_node(state: RunState) -> RunState:
        worker = cfg.worker_for("act")
        qa_log = state.get("qa_log", "")
        retry = bool(qa_log) and not state.get("qa_passed", False)
        plan_json = _plan_to_json(state.get("plan"))
        issue_ctx = _rvc_context(state.get("issue_id", ""), cfg.repo)
        logger.info("[act] starting implementation (retry=%s)", retry)
        prompt = (
            f"{state['contract']}\n\n"
            f"# LOCKED PLAN (immutable contract)\n{plan_json}\n\n"
            + (issue_ctx + "\n" if issue_ctx else "")
            + f"# TASK\n{state['task']}\n\n"
            + (f"# PREVIOUS QA FAILED — fix these failures:\n{qa_log[-4000:]}\n\n"
               if retry else "")
            + "Implement the locked plan now. Make the file changes. Keep changes "
              "minimal and aligned with the contract above."
        )
        res = worker.run(prompt, cwd=cfg.repo, timeout=1800)
        logger.info("[act] worker=%s ok=%s", res.worker, res.ok)
        return {
            "act_output": res.text,
            "status": "qa",
            "history": _log(state, "act", worker=res.worker, ok=res.ok,
                            retry=retry, cmd=res.cmd),
        }

    def qa_node(state: RunState) -> RunState:
        attempts = state.get("qa_attempts", 0) + 1
        logger.info("[qa] attempt %d", attempts)
        proc = subprocess.run(
            cfg.qa_cmd, cwd=str(cfg.repo), shell=True,
            capture_output=True, text=True, timeout=1800,
        )
        passed = proc.returncode == 0
        log = (proc.stdout + "\n" + proc.stderr).strip()
        logger.info("[qa] passed=%s returncode=%s", passed, proc.returncode)
        return {
            "qa_passed": passed,
            "qa_log": log,
            "qa_attempts": attempts,
            "status": "done" if passed else "qa",
            "history": _log(state, "qa", passed=passed, attempt=attempts,
                            returncode=proc.returncode),
        }

    def plan_reviser_node(state: RunState) -> RunState:
        """Stub: after max QA retries, diagnose whether the plan itself is wrong."""
        worker = cfg.worker_for("plan")
        plan_json = _plan_to_json(state.get("plan"))
        qa_log = state.get("qa_log", "")
        logger.info("[plan_reviser] diagnosing after %d failed QA attempts", state.get("qa_attempts", 0))
        prompt = (
            f"{state['contract']}\n\n"
            f"# CURRENT LOCKED PLAN\n{plan_json}\n\n"
            f"# TASK\n{state['task']}\n\n"
            f"# QA HAS FAILED REPEATEDLY\n{qa_log[-4000:]}\n\n"
            "Diagnose whether the failure is due to:\n"
            "1. A bad test_case (impossible to satisfy)\n"
            "2. An impossible expected_output / contract\n"
            "3. A node that is too large and needs splitting\n"
            "4. A genuine code bug (the coder's fault)\n\n"
            "If the plan or contract is wrong, emit a revised Plan JSON. "
            "If the code is at fault, emit the same Plan JSON with a note."
        )
        res = worker.run(prompt, cwd=cfg.repo, timeout=600)
        new_plan: Plan | None = None
        try:
            text = res.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            data = json.loads(text)
            new_plan = _json_to_plan(data)
        except Exception:
            pass

        if new_plan is not None and new_plan != state.get("plan"):
            logger.info("[plan_reviser] plan revised, new version")
            return {
                "plan": new_plan,
                "plan_locked": False,
                "qa_attempts": 0,
                "qa_passed": False,
                "qa_log": "",
                "status": "reviewing",
                "history": _log(state, "plan_revised",
                                worker=res.worker, ok=res.ok),
            }
        logger.warning("[plan_reviser] no revision possible, giving up")
        return {
            "status": "qa_failed",
            "history": _log(state, "plan_reviser_give_up",
                            worker=res.worker, ok=res.ok),
        }

    def commit_node(state: RunState) -> RunState:
        subject = state["task"].strip().splitlines()[0][:60]
        ttype = state.get("task_type", "feat")
        msg = cfg.commit_template.format(type=ttype, subject=subject)
        if state.get("issue_id"):
            msg += f" ({state['issue_id']})"
        logger.info("[commit] committing: %s", msg)
        subprocess.run(["git", "add", "-A"], cwd=str(cfg.repo), check=False)
        proc = subprocess.run(
            ["git", "commit", "-m", msg], cwd=str(cfg.repo),
            capture_output=True, text=True,
        )
        sha = ""
        if proc.returncode == 0:
            sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=str(cfg.repo),
                capture_output=True, text=True,
            ).stdout.strip()
            logger.info("[commit] sha=%s", sha)
        else:
            logger.warning("[commit] failed: %s", proc.stderr.strip()[:200])
        return {
            "commit_sha": sha,
            "status": "done",
            "history": _log(state, "commit", sha=sha, msg=msg,
                            ok=proc.returncode == 0),
        }

    # --- conditional edges ---
    def after_approve(state: RunState) -> Literal["act", "plan", "review", "end"]:
        st = state.get("status")
        if st == "rejected":
            return "plan" if state.get("rejection_note") else "end"
        if st == "reviewing":
            # human edited the plan — route back to reviewer
            return "review"
        return "act"

    def after_qa(state: RunState) -> Literal["commit", "act", "plan_reviser", "end"]:
        if state.get("qa_passed"):
            return "commit"
        if state.get("qa_attempts", 0) >= cfg.max_qa_retries:
            return "plan_reviser"
        return "act"

    def after_reviewer(state: RunState) -> Literal["approve", "plan"]:
        if state.get("plan_locked"):
            return "approve"
        return "plan"

    def after_plan_reviser(state: RunState) -> Literal["review", "end"]:
        if state.get("status") == "reviewing":
            return "review"
        return "end"

    g = StateGraph(RunState)
    g.add_node("plan", plan_node)
    g.add_node("review", reviewer_node)
    g.add_node("approve", approve_node)
    g.add_node("act", act_node)
    g.add_node("qa", qa_node)
    g.add_node("plan_reviser", plan_reviser_node)
    g.add_node("commit", commit_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "review")
    g.add_conditional_edges("review", after_reviewer,
                            {"approve": "approve", "plan": "plan"})
    g.add_conditional_edges("approve", after_approve,
                            {"act": "act", "plan": "plan", "review": "review", "end": END})
    g.add_edge("act", "qa")
    g.add_conditional_edges("qa", after_qa,
                            {"commit": "commit", "act": "act",
                             "plan_reviser": "plan_reviser", "end": END})
    g.add_conditional_edges("plan_reviser", after_plan_reviser,
                            {"review": "review", "end": END})
    g.add_edge("commit", END)
    return g

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
import time
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .projects_config import ProjectConfig
from .schema import Plan, TaskNode

logger = logging.getLogger("conductor.pipeline")

_STATE_DIR = Path(__file__).parent.parent / ".conductor"

def _save_raw_stdout(run_id: str, raw: str, node: str) -> None:
    """Append raw worker stdout to .conductor/logs/<run_id>.stdout.log."""
    if not run_id or not raw:
        return
    log_dir = _STATE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{run_id}.stdout.log"
    with open(path, "a") as f:
        f.write(f"\n{'=' * 60}\n=== {node} ===\n")
        f.write(raw)
        if not raw.endswith("\n"):
            f.write("\n")
    logger.info("[%s] raw stdout saved to %s", node, path)


class RunState(TypedDict, total=False):
    # --- inputs ---
    project: str
    run_id: str                # durable run id (for file paths)
    task: str                  # the user's task description
    task_type: str             # conventional-commit type: feat|fix|refactor|...
    issue_id: str              # RVC/vault issue id, e.g. STORY-83 (optional)
    rvc_mode: str              # "full" (default), "get", or "off"
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
    except Exception as e:
        logger.error("[git_context] failed to get branch: %s", e, exc_info=True)
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        ).stdout.strip()
        if log:
            ctx.append(f"Recent commits:\n{log}")
    except Exception as e:
        logger.error("[git_context] failed to get git log: %s", e, exc_info=True)
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        ).stdout.strip()
        if status:
            ctx.append(f"Uncommitted changes:\n{status}")
    except Exception as e:
        logger.error("[git_context] failed to get git status: %s", e, exc_info=True)
    return "\n".join(ctx)


def _rvc_context(issue_id: str, repo: Path, mode: str = "full") -> str:
    """Fetch RVC vault context for an issue via the rvc CLI.

    Falls back to ~/.local/bin/rvc if rvc is not on PATH.
    Returns empty string on failure so the pipeline never breaks.

    mode: "full" = rvc context (issue + all linked docs, ~80K chars)
          "get"  = rvc get (issue file only, ~2K chars)
          "off"  = skip RVC entirely
    """
    if not issue_id or mode == "off":
        return ""
    rvc_bin = "rvc"
    if subprocess.run(["which", rvc_bin], capture_output=True).returncode != 0:
        fallback = Path.home() / ".local" / "bin" / "rvc"
        if fallback.exists():
            rvc_bin = str(fallback)
        else:
            logger.warning("[rvc] binary not found on PATH or at %s", fallback)
            return ""
    try:
        cmd = [rvc_bin, "get", issue_id] if mode == "get" else [rvc_bin, "context", issue_id]
        proc = subprocess.run(
            cmd, cwd=str(repo), capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            logger.info("[rvc] fetched %s for %s (%d chars)", mode, issue_id, len(proc.stdout))
            return f"# RVC ISSUE CONTEXT ({issue_id}, mode={mode})\n{proc.stdout.strip()}\n"
        else:
            logger.warning("[rvc] %s fetch failed for %s (exit=%d, stderr %d chars):\n%s",
                           mode, issue_id, proc.returncode, len(proc.stderr), proc.stderr.strip()[-1000:])
    except Exception as e:
        logger.error("[rvc] exception fetching %s for %s: %s", mode, issue_id, e, exc_info=True)
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
        logger.info("[plan] entering (status=%s qa_attempts=%s)", state.get("status"), state.get("qa_attempts", 0))
        logger.info("[plan] starting plan generation")
        contract = _read_contract(cfg)
        worker = cfg.worker_for("plan")
        rej = state.get("rejection_note", "")
        git_ctx = _git_context(cfg.repo)
        issue_ctx = _rvc_context(state.get("issue_id", ""), cfg.repo, state.get("rvc_mode", "full"))
        logger.info("[plan] prompt breakdown: agents_md=%d rvc=%d git=%d task=%d rej=%d",
                     len(contract), len(issue_ctx), len(git_ctx),
                     len(state["task"]), len(rej))
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
        logger.info("[plan] worker=%s model=%s timeout=600 prompt_len=%d",
                     worker.name, worker.model, len(prompt))
        res = worker.run(prompt, cwd=cfg.repo, timeout=600)
        _save_raw_stdout(state.get("run_id", ""), res.raw, "plan")
        logger.info("[plan] worker result: ok=%s returncode=%s len=%d error=%s",
                     res.ok, res.returncode, len(res.text), res.error or "none")
        if not res.ok:
            logger.error("[plan] worker returned error:\n%s", res.error)
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
            logger.error("[plan] failed to parse planner output (%d chars): %s",
                         len(res.text), e, exc_info=True)
            logger.error("[plan] raw worker output (first 1000 chars):\n%s",
                         res.text[:1000])

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
        logger.info("[review] entering (status=%s)", state.get("status"))
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
            logger.warning("[review] reject: %d validation errors:\n%s", len(errors), "\n".join(f"  - {e}" for e in errors))
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
        plan_obj = state.get("plan")
        if plan_obj:
            logger.info("[approve] entering: plan=%s v%d nodes=%d",
                        plan_obj.id, plan_obj.version, len(plan_obj.nodes))
        else:
            logger.warning("[approve] entering: no plan present!")
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
                    logger.error("[approve] human edit was invalid: %s", e, exc_info=True)
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
        issue_ctx = _rvc_context(state.get("issue_id", ""), cfg.repo, state.get("rvc_mode", "full"))
        logger.info("[act] prompt breakdown: contract=%d plan=%d rvc=%d task=%d qa_log=%d",
                     len(state["contract"]), len(plan_json),
                     len(issue_ctx), len(state["task"]), len(qa_log))
        logger.info("[act] entering (status=%s qa_attempts=%s)", state.get("status"), state.get("qa_attempts", 0))
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
        logger.info("[act] worker=%s model=%s timeout=1800 retry=%s prompt_len=%d",
                     worker.name, worker.model, retry, len(prompt))
        res = worker.run(prompt, cwd=cfg.repo, timeout=1800)
        _save_raw_stdout(state.get("run_id", ""), res.raw, "act")
        logger.info("[act] worker result: ok=%s returncode=%s len=%d error=%s",
                     res.ok, res.returncode, len(res.text), res.error or "none")
        if not res.ok:
            logger.error("[act] worker returned error:\n%s", res.error)
            logger.error("[act] raw worker output (first 1000 chars):\n%s", res.text[:1000])
        return {
            "act_output": res.text,
            "status": "qa",
            "history": _log(state, "act", worker=res.worker, ok=res.ok,
                            retry=retry, cmd=res.cmd),
        }

    def qa_node(state: RunState) -> RunState:
        attempts = state.get("qa_attempts", 0) + 1
        logger.info("[qa] entering (attempt=%d/%d cmd=%s)",
                     attempts, cfg.max_qa_retries, cfg.qa_cmd)
        logger.info("[qa] attempt %d: running %s", attempts, cfg.qa_cmd)
        t0 = time.monotonic()
        logger.info("[qa] waiting for tests...")
        proc = subprocess.run(
            cfg.qa_cmd, cwd=str(cfg.repo), shell=True,
            capture_output=True, text=True, timeout=1800,
        )
        elapsed = time.monotonic() - t0
        passed = proc.returncode == 0
        log = (proc.stdout + "\n" + proc.stderr).strip()
        logger.info("[qa] done in %.1fs: passed=%s returncode=%s stdout_len=%d stderr_len=%d",
                     elapsed, passed, proc.returncode, len(proc.stdout or ""), len(proc.stderr or ""))
        if not passed:
            logger.error("[qa] FAILED after %.1fs (stdout+stderr %d chars):\n%s",
                         elapsed, len(log), log[-2000:])
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
        logger.info("[plan_reviser] entering (status=%s qa_attempts=%s)",
                     state.get("status"), state.get("qa_attempts", 0))
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
        logger.info("[plan_reviser] worker=%s model=%s timeout=600 prompt_len=%d",
                     worker.name, worker.model, len(prompt))
        res = worker.run(prompt, cwd=cfg.repo, timeout=600)
        _save_raw_stdout(state.get("run_id", ""), res.raw, "plan_reviser")
        logger.info("[plan_reviser] worker result: ok=%s returncode=%s len=%d error=%s",
                     res.ok, res.returncode, len(res.text), res.error or "none")
        if not res.ok:
            logger.error("[plan_reviser] worker returned error:\n%s", res.error)
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
        except Exception as e:
            logger.error("[plan_reviser] failed to parse worker output (%d chars): %s",
                         len(res.text), e, exc_info=True)
            logger.error("[plan_reviser] raw worker output (first 1000 chars):\n%s",
                         res.text[:1000])

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
        logger.error("[plan_reviser] no revision possible, giving up")
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
        logger.info("[commit] entering (status=%s qa_passed=%s)", state.get("status"), state.get("qa_passed"))
        logger.info("[commit] running: git add -A && git commit -m \"%s\"", msg)
        add_proc = subprocess.run(["git", "add", "-A"], cwd=str(cfg.repo), check=False,
                                   capture_output=True, text=True)
        if add_proc.returncode != 0:
            logger.warning("[commit] git add stderr (if any): %s", add_proc.stderr.strip()[-500:])
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
            logger.info("[commit] git commit stdout: %s", proc.stdout.strip())
        else:
            logger.warning("[commit] failed (exit=%d, stderr %d chars):\n%s",
                           proc.returncode, len(proc.stderr), proc.stderr.strip()[-1000:])
        return {
            "commit_sha": sha,
            "status": "done",
            "history": _log(state, "commit", sha=sha, msg=msg,
                            ok=proc.returncode == 0),
        }

    # --- conditional edges ---
    def after_approve(state: RunState) -> Literal["act", "plan", "review", "end"]:
        st = state.get("status")
        note = state.get("rejection_note", "")
        logger.info("[route] after_approve: status=%s rejection_note=%s", st, repr(note[:200]) if note else "none")
        if st == "rejected":
            target = "plan" if note else "end"
            logger.info("[route] after_approve -> %s (rejected%s)", target,
                        " with note → re-plan" if note else " without note → end")
            return target
        if st == "reviewing":
            logger.info("[route] after_approve -> review (human edited plan)")
            return "review"
        logger.info("[route] after_approve -> act (approved)")
        return "act"

    def after_qa(state: RunState) -> Literal["commit", "act", "plan_reviser", "end"]:
        passed = state.get("qa_passed")
        attempts = state.get("qa_attempts", 0)
        max_retries = cfg.max_qa_retries
        logger.info("[route] after_qa: passed=%s attempts=%d/%d", passed, attempts, max_retries)
        if passed:
            logger.info("[route] after_qa -> commit (QA passed)")
            return "commit"
        if attempts >= max_retries:
            logger.warning("[route] after_qa -> plan_reviser (QA failed %d times, max=%d)", attempts, max_retries)
            return "plan_reviser"
        logger.info("[route] after_qa -> act (QA failed, retry %d/%d)", attempts, max_retries)
        return "act"

    def after_reviewer(state: RunState) -> Literal["approve", "plan"]:
        locked = state.get("plan_locked")
        logger.info("[route] after_reviewer: plan_locked=%s", locked)
        if locked:
            logger.info("[route] after_reviewer -> approve (plan locked)")
            return "approve"
        logger.warning("[route] after_reviewer -> plan (plan invalid, re-planning)")
        return "plan"

    def after_plan_reviser(state: RunState) -> Literal["review", "end"]:
        st = state.get("status")
        logger.info("[route] after_plan_reviser: status=%s", st)
        if st == "reviewing":
            logger.info("[route] after_plan_reviser -> review (plan was revised)")
            return "review"
        logger.warning("[route] after_plan_reviser -> end (plan revision failed or unchanged)")
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

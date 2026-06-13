"""The LangGraph pipeline: Plan -> Approve -> Act -> QA -> Commit.

State is the durable run ledger, checkpointed to SQLite so any run is
resumable and time-travel debuggable. The human-approval gate uses
LangGraph's native `interrupt()` — the graph pauses, persists, and resumes
on a `Command(resume=...)` with the human's decision.

The QA node is the conditional heart: on failure it routes back to ACT
(feeding the failure log to the fixing worker) until max_qa_retries, then
gives up with status=qa_failed. This retry edge is exactly why LangGraph
earns its place over a flat dispatcher.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .projects_config import ProjectConfig


class RunState(TypedDict, total=False):
    # --- inputs ---
    project: str
    task: str                  # the user's task description
    task_type: str             # conventional-commit type: feat|fix|refactor|...
    issue_id: str              # RVC/vault issue id, e.g. STORY-83 (optional)
    # --- accumulated ledger ---
    contract: str              # AGENTS.md content injected into every worker
    plan: str                  # output of the PLAN node
    approved: bool             # human gate result
    rejection_note: str        # if human rejects, why (fed back to planner)
    act_output: str            # latest ACT worker output
    qa_passed: bool
    qa_log: str                # latest QA stdout+stderr
    qa_attempts: int
    commit_sha: str
    status: str                # planning|awaiting_approval|acting|qa|done|qa_failed|rejected
    history: list              # append-only event log for the ledger


def _read_contract(cfg: ProjectConfig) -> str:
    if cfg.agents_md.exists():
        return cfg.agents_md.read_text()
    return "(no AGENTS.md found — operate conservatively)"


def _log(state: RunState, event: str, **data) -> list:
    h = list(state.get("history", []))
    h.append({"event": event, **data})
    return h


def build_graph(cfg: ProjectConfig):
    """Compile the pipeline for a given project config."""

    def plan_node(state: RunState) -> RunState:
        contract = _read_contract(cfg)
        worker = cfg.worker_for("plan")
        rej = state.get("rejection_note", "")
        prompt = (
            f"{contract}\n\n"
            f"# TASK TO PLAN\n{state['task']}\n\n"
            + (f"# PRIOR PLAN WAS REJECTED — address this feedback:\n{rej}\n\n" if rej else "")
            + "Produce a concrete, numbered implementation plan. Do NOT write "
              "code or modify files — planning only. List files to touch, the "
              "approach, and how it will be verified."
        )
        res = worker.run(prompt, cwd=cfg.repo, timeout=600)
        return {
            "contract": contract,
            "plan": res.text,
            "status": "awaiting_approval",
            "history": _log(state, "plan",
                            worker=res.worker, ok=res.ok, cmd=res.cmd),
        }

    def approve_node(state: RunState) -> RunState:
        # Native LangGraph human-in-the-loop: pause + persist, resume w/ decision.
        decision = interrupt({
            "type": "approval_request",
            "plan": state.get("plan", ""),
            "task": state.get("task", ""),
        })
        # `decision` is whatever the resuming Command(resume=...) supplies.
        if isinstance(decision, dict):
            approved = bool(decision.get("approved"))
            note = decision.get("note", "")
        else:
            approved = bool(decision)
            note = ""
        if approved:
            return {"approved": True, "status": "acting",
                    "history": _log(state, "approved")}
        return {"approved": False, "rejection_note": note, "status": "rejected",
                "history": _log(state, "rejected", note=note)}

    def act_node(state: RunState) -> RunState:
        worker = cfg.worker_for("act")
        qa_log = state.get("qa_log", "")
        retry = bool(qa_log) and not state.get("qa_passed", False)
        prompt = (
            f"{state['contract']}\n\n"
            f"# APPROVED PLAN\n{state.get('plan','')}\n\n"
            f"# TASK\n{state['task']}\n\n"
            + (f"# PREVIOUS QA FAILED — fix these failures:\n{qa_log[-4000:]}\n\n"
               if retry else "")
            + "Implement the plan now. Make the file changes. Keep changes "
              "minimal and aligned with the contract above."
        )
        res = worker.run(prompt, cwd=cfg.repo, timeout=1800)
        return {
            "act_output": res.text,
            "status": "qa",
            "history": _log(state, "act", worker=res.worker, ok=res.ok,
                            retry=retry, cmd=res.cmd),
        }

    def qa_node(state: RunState) -> RunState:
        attempts = state.get("qa_attempts", 0) + 1
        proc = subprocess.run(
            cfg.qa_cmd, cwd=str(cfg.repo), shell=True,
            capture_output=True, text=True, timeout=1800,
        )
        passed = proc.returncode == 0
        log = (proc.stdout + "\n" + proc.stderr).strip()
        return {
            "qa_passed": passed,
            "qa_log": log,
            "qa_attempts": attempts,
            "status": "done" if passed else "qa",
            "history": _log(state, "qa", passed=passed, attempt=attempts,
                            returncode=proc.returncode),
        }

    def commit_node(state: RunState) -> RunState:
        subject = state["task"].strip().splitlines()[0][:60]
        ttype = state.get("task_type", "feat")
        msg = cfg.commit_template.format(type=ttype, subject=subject)
        if state.get("issue_id"):
            msg += f" ({state['issue_id']})"
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
        return {
            "commit_sha": sha,
            "status": "done",
            "history": _log(state, "commit", sha=sha, msg=msg,
                            ok=proc.returncode == 0),
        }

    # --- conditional edges ---
    def after_approve(state: RunState) -> Literal["act", "plan", "end"]:
        if state.get("status") == "rejected":
            # rejected with a note -> replan; rejected hard -> stop
            return "plan" if state.get("rejection_note") else "end"
        return "act"

    def after_qa(state: RunState) -> Literal["commit", "act", "end"]:
        if state.get("qa_passed"):
            return "commit"
        if state.get("qa_attempts", 0) >= cfg.max_qa_retries:
            return "end"          # give up: status stays "qa", qa_failed reported by runner
        return "act"              # the retry edge

    g = StateGraph(RunState)
    g.add_node("plan", plan_node)
    g.add_node("approve", approve_node)
    g.add_node("act", act_node)
    g.add_node("qa", qa_node)
    g.add_node("commit", commit_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "approve")
    g.add_conditional_edges("approve", after_approve,
                            {"act": "act", "plan": "plan", "end": END})
    g.add_edge("act", "qa")
    g.add_conditional_edges("qa", after_qa,
                            {"commit": "commit", "act": "act", "end": END})
    g.add_edge("commit", END)
    return g

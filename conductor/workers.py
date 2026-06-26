"""CLI worker adapter — invoke coding CLIs headless, return structured output.

The anti-siloing core: every worker is STATELESS. It receives the full brief
(AGENTS.md contract + task + relevant context) on each call and returns its
output. No worker keeps private session memory across pipeline nodes — all
durable state lives in the run ledger and the RVC vault.

Supported workers (verified headless modes):
  claude    -> `claude -p <prompt> --output-format stream-json`  (structured)
  gemini    -> `gemini -p <prompt> [--approval-mode plan|yolo]`    (plan = read-only)
  qwen      -> `qwen <prompt> -o stream-json`                      (structured, positional)
  opencode  -> `opencode run <prompt>`                             (plain text)
"""
from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("conductor.workers")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    # CSI sequences (most common)
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


@dataclass
class WorkerResult:
    worker: str
    ok: bool
    text: str                      # final assistant text, best-effort extracted
    raw: str                       # full stdout (for the ledger / debugging)
    returncode: int
    cmd: str
    error: str = ""


@dataclass
class Worker:
    """One coding CLI, invoked headless. `name` is the binary on PATH.

    Parameters
    ----------
    name:
        Binary name on PATH — ``claude``, ``gemini``, ``qwen``, ``opencode``, …
    model:
        Model identifier passed to the CLI via its native ``-m`` / ``--model``
        flag (agentic-dependent).  ``None`` = let the CLI use its default.
    extra_args:
        Additional CLI arguments appended after the built-in ones.
    read_only:
        When ``True``, the worker is forbidden from writing files.  Supported
        by ``gemini`` (``--approval-mode plan``) and ``qwen``
        (``--approval-mode plan``).  Ignored for ``claude`` and ``opencode``.
    """
    name: str
    model: str | None = None
    extra_args: list[str] = field(default_factory=list)
    read_only: bool = False

    # ------------------------------------------------------------------ #
    # Command construction
    # ------------------------------------------------------------------ #
    def _build_cmd(self, prompt: str) -> list[str]:
        n = self.name

        if n == "claude":
            cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
            if self.model:
                cmd += ["-m", self.model]
            return cmd + self.extra_args

        if n == "gemini":
            cmd = ["gemini", "-p", prompt]
            if self.read_only:
                cmd += ["--approval-mode", "plan"]
            if self.model:
                cmd += ["-m", self.model]
            return cmd + self.extra_args

        if n == "qwen":
            # Positional query (preferred over deprecated -p) + structured output.
            cmd = ["qwen", prompt, "-o", "stream-json"]
            if self.read_only:
                cmd += ["--approval-mode", "plan"]
            if self.model:
                cmd += ["-m", self.model]
            return cmd + self.extra_args

        if n == "opencode":
            # `opencode run [message..]` is the headless entry-point.
            cmd = ["opencode", "run", prompt]
            if self.model:
                cmd += ["-m", self.model]
            # opencode does not expose --approval-mode in current versions;
            # read_only is intentionally ignored here.
            return cmd + self.extra_args

        # Generic fallback: assume `-p` headless convention
        cmd = [n, "-p", prompt]
        if self.model:
            cmd += ["-m", self.model]
        return cmd + self.extra_args

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def run(self, prompt: str, cwd: str | Path, timeout: int = 1800,
            env: dict | None = None) -> WorkerResult:
        cmd = self._build_cmd(prompt)
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        logger.info("[worker:%s] running (timeout=%d, prompt_len=%d, cwd=%s)",
                     self.name, timeout, len(prompt), cwd)
        logger.debug("[worker:%s] command: %s", self.name, cmd_str[:2000])
        logger.debug("[worker:%s] prompt preview (first 500 chars):\n%s",
                     self.name, prompt[:500])
        logger.debug("[worker:%s] prompt preview (last 500 chars):\n%s",
                     self.name, prompt[-500:])
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True,
                timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired as e:
            partial = e.stdout
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            logger.warning("[worker:%s] TIMEOUT after %ds (partial stdout=%d chars)",
                           self.name, timeout, len(partial or ""))
            return WorkerResult(self.name, False, "", partial or "", -1,
                                cmd_str, error=f"timeout after {timeout}s")
        except FileNotFoundError:
            logger.error("[worker:%s] binary not found on PATH", self.name)
            return WorkerResult(self.name, False, "", "", -127, cmd_str,
                                error=f"worker binary not found: {self.name}")
        text = self._extract_text(proc.stdout)
        ok = proc.returncode == 0
        stderr = proc.stderr.strip()
        if stderr:
            logger.debug("[worker:%s] stderr (%d chars):\n%s",
                         self.name, len(stderr), stderr[-2000:])
        logger.info("[worker:%s] done: returncode=%d ok=%s stdout_len=%d text_len=%d stderr_len=%d",
                     self.name, proc.returncode, ok, len(proc.stdout or ""), len(text), len(stderr))
        if not ok:
            error_msg = stderr[-10000:] or "nonzero exit"
            logger.warning("[worker:%s] FAILED (%d chars stderr):\n%s",
                           self.name, len(stderr), error_msg)
        else:
            error_msg = ""
        return WorkerResult(
            self.name, ok, text, proc.stdout, proc.returncode, cmd_str,
            error=error_msg,
        )

    # ------------------------------------------------------------------ #
    # Output parsing
    # ------------------------------------------------------------------ #
    def _extract_text(self, stdout: str) -> str:
        """Pull the final assistant text out of worker stdout."""
        if self.name in ("claude", "qwen"):
            # Both CLIs support `-o stream-json` (newline-delimited events).
            # We try the same best-effort parser; if the format diverges we
            # fall back to raw stdout.
            return self._extract_stream_json(stdout)
        if self.name == "opencode":
            # opencode prints ANSI escape codes and a header line like
            # "> build · provider/model". Strip those artefacts.
            cleaned = _strip_ansi(stdout)
            lines = cleaned.splitlines()
            # Drop header lines that start with "> build"
            while lines and lines[0].strip().startswith("> build"):
                lines = lines[1:]
            return "\n".join(lines).strip()
        # gemini / generic: plain text on stdout
        return stdout.strip()

    @staticmethod
    def _extract_stream_json(stdout: str) -> str:
        """Parse newline-delimited JSON events from stream-json output."""
        final: list[str] = []
        result_field: str | None = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            # claude-style result envelope
            if ev.get("type") == "result" and "result" in ev:
                result_field = ev["result"]
            # assistant message content blocks (claude & qwen-compatible)
            msg = ev.get("message", {})
            for block in (msg.get("content") or []):
                if isinstance(block, dict) and block.get("type") == "text":
                    final.append(block.get("text", ""))
            # qwen may emit content directly in some event shapes
            if isinstance(ev.get("content"), str):
                final.append(ev["content"])
        if result_field:
            return result_field
        parsed = "\n".join(final).strip()
        return parsed or stdout.strip()


# ---------------------------------------------------------------------------
# Worker factory — the canonical way to build a Worker for any agentic CLI.
# ---------------------------------------------------------------------------

def create_worker(
    agentic: str,
    model: str | None = None,
    extra_args: list[str] | None = None,
    read_only: bool = False,
) -> Worker:
    """Create a :class:`Worker` for the given agentic CLI.

    Parameters
    ----------
    agentic:
        The agentic tool to use — ``"claude"``, ``"gemini"``, ``"qwen"``,
        ``"opencode"``, or any other binary name on PATH.
    model:
        Model identifier in the format the CLI expects (e.g.
        ``"anthropic/claude-sonnet-4-20250514"`` for opencode,
        ``"qwen3-5plus"`` for qwen).  ``None`` = CLI default.
    extra_args:
        Additional CLI arguments (e.g. ``["--yolo"]`` for qwen).
    read_only:
        If ``True``, request a read-only / planning mode when the CLI
        supports it (gemini, qwen).

    Returns
    -------
    Worker
        Ready-to-run worker instance.
    """
    return Worker(
        name=agentic,
        model=model,
        extra_args=list(extra_args) if extra_args else [],
        read_only=read_only,
    )


# ---------------------------------------------------------------------------
# Legacy dynamic-config table (kept for backward compat with old pipelines).
# New code should prefer :func:`create_worker`.
# ---------------------------------------------------------------------------
WORKER_CONFIG: dict[str, dict] = {
    "qwencode": {"agentic": "qwen", "model": "qwen3-5plus", "extra_args": []},
    "opencode": {"agentic": "opencode", "model": None, "extra_args": []},
}


def workerInit(name: str, model: str, extra_args: list[str] | None = None) -> Worker:
    """Deprecated — use :func:`create_worker` instead.

    Kept for backward compatibility with existing project configs that call
    ``workerInit`` directly or store entries in ``WORKER_CONFIG``.
    """
    if extra_args is None:
        extra_args = []
    WORKER_CONFIG[name] = {
        "agentic": name,
        "model": model,
        "extra_args": [model] + extra_args,
    }
    return create_worker(agentic=name, model=model, extra_args=extra_args)


# ---------------------------------------------------------------------------
# Default routing table — overridable per project in projects/<name>.toml
# ---------------------------------------------------------------------------
DEFAULT_ROUTING = {
    "plan":   create_worker("gemini", read_only=True),   # read-only planner
    "act":    create_worker("claude"),                    # careful implementer
    "bulk":   create_worker("qwen"),                     # high-volume mechanical edits
    "review": create_worker("claude"),                   # code review / QA reasoning
}

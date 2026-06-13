"""CLI worker adapter — invoke coding CLIs headless, return structured output.

The anti-siloing core: every worker is STATELESS. It receives the full brief
(AGENTS.md contract + task + relevant context) on each call and returns its
output. No worker keeps private session memory across pipeline nodes — all
durable state lives in the run ledger and the RVC vault.

Supported workers (verified headless modes):
  claude  -> `claude -p <prompt> --output-format stream-json`  (structured)
  gemini  -> `gemini -p <prompt> [--approval-mode plan|yolo]`   (plan = read-only)
  qwen    -> `qwen -p <prompt>`                                 (one-shot)
"""
from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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
    """One coding CLI, invoked headless. `name` is the binary on PATH."""
    name: str                                  # claude | gemini | qwen
    extra_args: list[str] = field(default_factory=list)
    read_only: bool = False                    # planning workers must not write

    def _build_cmd(self, prompt: str) -> list[str]:
        n = self.name
        if n == "claude":
            # stream-json gives us a parseable event stream; --print = headless
            return ["claude", "-p", prompt,
                    "--output-format", "stream-json", "--verbose",
                    *self.extra_args]
        if n == "gemini":
            args = ["gemini", "-p", prompt]
            # plan mode = read-only (safe for the PLAN node); yolo for autonomous ACT
            if self.read_only:
                args += ["--approval-mode", "plan"]
            args += self.extra_args
            return args
        if n == "qwen":
            return ["qwen", "-p", prompt, *self.extra_args]
        # generic fallback: assume `-p` headless convention
        return [n, "-p", prompt, *self.extra_args]

    def run(self, prompt: str, cwd: str | Path, timeout: int = 1800,
            env: dict | None = None) -> WorkerResult:
        cmd = self._build_cmd(prompt)
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True,
                timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired as e:
            partial = e.stdout
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            return WorkerResult(self.name, False, "", partial or "", -1,
                                cmd_str, error=f"timeout after {timeout}s")
        except FileNotFoundError:
            return WorkerResult(self.name, False, "", "", -127, cmd_str,
                                error=f"worker binary not found: {self.name}")
        text = self._extract_text(proc.stdout)
        ok = proc.returncode == 0
        return WorkerResult(
            self.name, ok, text, proc.stdout, proc.returncode, cmd_str,
            error="" if ok else (proc.stderr.strip()[-2000:] or "nonzero exit"),
        )

    def _extract_text(self, stdout: str) -> str:
        """Pull the final assistant text out of worker stdout."""
        if self.name == "claude":
            # stream-json: newline-delimited events; final result in a
            # {"type":"result","result":"..."} or assistant text deltas.
            final = []
            result_field = None
            for line in stdout.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "result" and "result" in ev:
                    result_field = ev["result"]
                # assistant message content blocks
                msg = ev.get("message", {})
                for block in (msg.get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        final.append(block.get("text", ""))
            if result_field:
                return result_field
            return "\n".join(final).strip() or stdout.strip()
        # gemini / qwen: plain text on stdout
        return stdout.strip()


# Default routing table — overridable per project in projects/<name>.toml
DEFAULT_ROUTING = {
    "plan":  Worker("gemini", read_only=True),   # read-only planner
    "act":   Worker("claude"),                   # careful implementer
    "bulk":  Worker("qwen"),                      # high-volume mechanical edits
    "review": Worker("claude"),                   # code review / QA reasoning
}

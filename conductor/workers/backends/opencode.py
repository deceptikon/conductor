"""Opencode CLI backend."""
from __future__ import annotations

from dataclasses import dataclass

from ..base import _strip_ansi


@dataclass
class OpencodeBackend:
    name: str = "opencode"

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        cmd = ["opencode", "run", prompt]
        if model:
            cmd += ["-m", model]
        return cmd + extra_args

    def extract_text(self, stdout: str) -> str:
        cleaned = _strip_ansi(stdout)
        lines = cleaned.splitlines()
        while lines and lines[0].strip().startswith("> build"):
            lines = lines[1:]
        return "\n".join(lines).strip()

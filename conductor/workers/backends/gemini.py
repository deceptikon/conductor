"""Gemini CLI backend."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeminiBackend:
    name: str = "gemini"

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        cmd = ["gemini", "-p", prompt]
        if read_only:
            cmd += ["--approval-mode", "plan"]
        if model:
            cmd += ["-m", model]
        return cmd + extra_args

    def extract_text(self, stdout: str) -> str:
        return stdout.strip()

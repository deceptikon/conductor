"""Generic CLI fallback backend for unknown worker names."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GenericCLIBackend:
    name: str = "generic"

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        cmd = [self.name, "-p", prompt]
        if model:
            cmd += ["-m", model]
        return cmd + extra_args

    def extract_text(self, stdout: str) -> str:
        return stdout.strip()


@dataclass
class GenericOpenAIBackend:
    """Backend that talks to an OpenAI-compatible HTTP endpoint.

    Defaults to the local server at ``127.0.0.1:22222`` and model
    ``gemma4-coding-q4_k_m.gguf``.
    """

    name: str = "openai-generic"
    base_url: str = "http://127.0.0.1:22222/v1"

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        model = model or "gemma4-coding-q4_k_m.gguf"
        runner = Path(__file__).with_name("_openai_generic.py")
        cmd = [
            sys.executable,
            str(runner),
            "--base-url",
            self.base_url,
            "--model",
            model,
            prompt,
        ]
        return cmd + extra_args

    def extract_text(self, stdout: str) -> str:
        return stdout.strip()

"""Qwen CLI backend."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..base import extract_stream_json

logger = logging.getLogger("conductor.workers")


@dataclass
class QwenBackend:
    name: str = "qwen"

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        cmd = ["qwen", prompt, "-o", "stream-json"]
        if read_only:
            cmd += ["--approval-mode", "plan"]
        if model:
            cmd += ["-m", model]
        return cmd + extra_args

    def extract_text(self, stdout: str) -> str:
        result, dropped = extract_stream_json(stdout, return_dropped=True)
        if dropped:
            logger.info(
                "[worker:%s] extract_stream_json dropped %d non-JSON lines",
                self.name,
                len(dropped),
            )
            logger.debug(
                "[worker:%s] dropped lines preview:\n%s",
                self.name,
                "\n".join(dropped[:5]),
            )
        return result

"""Built-in worker backends.

Importing this module auto-registers all built-in backends into the global
:class:`~conductor.workers.base.registry` singleton.
"""
from __future__ import annotations

from ..base import registry
from .claude import ClaudeBackend
from .gemini import GeminiBackend
from .generic import GenericCLIBackend, GenericOpenAIBackend
from .opencode import OpencodeBackend
from .qwen import QwenBackend

# Auto-register built-in backends
registry.register(ClaudeBackend())
registry.register(GeminiBackend())
registry.register(QwenBackend())
registry.register(OpencodeBackend())
registry.register(GenericCLIBackend())
registry.register(GenericOpenAIBackend())

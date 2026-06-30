"""conductor.workers — model-agnostic worker orchestration.

Public API surface.  Importing this module triggers auto-registration of all
built-in backends into the module-level :data:`registry` singleton.

Example::

    from conductor.workers import launch_worker, registry, WorkerBackend

    # Launch a built-in worker
    result = launch_worker("claude", "Refactor this function")

    # Register a custom backend from an external app
    @dataclass
    class MySDK(WorkerBackend):
        name: str = "my-sdk"
        def build_cmd(self, prompt, model, extra_args, read_only): ...
        def extract_text(self, stdout): ...

    registry.register(MySDK())
    result = launch_worker("my-sdk", "Do the thing")
"""
from __future__ import annotations

# Trigger auto-registration of built-in backends
from . import backends  # noqa: F401

# Re-export the public API surface
from .base import WorkerBackend, WorkerResult, registry  # noqa: F401
from .executor import DashMode, Worker  # noqa: F401
from .launch import DEFAULT_ROUTING, create_worker, launch_worker  # noqa: F401

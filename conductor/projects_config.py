"""Per-project configuration. The harness is generic; each project it drives
is described by a TOML file under conductor/projects/<name>.toml.

ADLAI is project #1. Add more by dropping another TOML in projects/.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .workers import Worker, create_worker

PROJECTS_DIR = Path(__file__).parent / "projects"


@dataclass
class ProjectConfig:
    name: str
    repo: Path                       # working dir where CLIs run
    vault: Path                      # RVC/Obsidian vault path
    qa_cmd: str                      # the QA gate command (must exit 0)
    agents_md: Path                  # canonical contract file
    routing: dict[str, Worker] = field(default_factory=dict)
    commit_template: str = "{type}: {subject}"
    max_qa_retries: int = 2

    @classmethod
    def load(cls, name: str) -> "ProjectConfig":
        path = PROJECTS_DIR / f"{name}.toml"
        if not path.exists():
            raise FileNotFoundError(f"no project config: {path}")
        data = tomllib.loads(path.read_text())
        p = data["project"]
        repo = Path(p["repo"]).expanduser()
        routing = {}
        for node, spec in (data.get("routing") or {}).items():
            routing[node] = create_worker(
                agentic=spec["worker"],
                model=spec.get("model"),
                extra_args=spec.get("extra_args", []),
                read_only=spec.get("read_only", False),
                dash_mode=spec.get("dash_mode", "sh"),
            )
        return cls(
            name=p["name"],
            repo=repo,
            vault=Path(p["vault"]).expanduser(),
            qa_cmd=p["qa_cmd"],
            agents_md=Path(p.get("agents_md", repo / "AGENTS.md")).expanduser(),
            routing=routing,
            commit_template=p.get("commit_template", "{type}: {subject}"),
            max_qa_retries=int(p.get("max_qa_retries", 2)),
        )

    def worker_for(self, node: str) -> Worker:
        """Return the :class:`~conductor.workers.Worker` for a pipeline node.

        The lookup order is:
        1. Project‑specific routing defined in the TOML file (``self.routing``).
        2. The static ``DEFAULT_ROUTING`` fallback.
        """
        from .workers import DEFAULT_ROUTING

        # 1. Project‑specific routing
        if node in self.routing:
            return self.routing[node]

        # 2. Fallback to the built‑in defaults
        return DEFAULT_ROUTING[node]

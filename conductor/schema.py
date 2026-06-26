"""Structured plan schema.

The Plan is the contract. Once locked, it is immutable.

NOTE: Contract is currently a simple expected_output string.
Structured contracts (JSONSchema, function signatures) are deferred to a later
phase so we can validate the core pipeline mechanics first.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskNode:
    id: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    expected_output: str = ""       # contract for the coder (string for now)
    test_case: str = ""             # contract for the QA runner
    artifact_path: str | None = None


@dataclass
class Plan:
    id: str
    version: int
    nodes: list[TaskNode] = field(default_factory=list)
    topo_order: list[str] = field(default_factory=list)

    def node_map(self) -> dict[str, TaskNode]:
        return {n.id: n for n in self.nodes}

    def validate(self) -> list[str]:
        """Return a list of validation errors. Empty list means valid."""
        errors: list[str] = []
        node_ids = {n.id for n in self.nodes}

        # 1. Every dependency must exist
        for node in self.nodes:
            for dep in node.dependencies:
                if dep not in node_ids:
                    errors.append(f"Node '{node.id}' depends on unknown node '{dep}'")

        # 2. No cycles (Kahn's algorithm) — only on valid deps
        in_degree = {n.id: 0 for n in self.nodes}
        adj = {n.id: [] for n in self.nodes}
        for node in self.nodes:
            for dep in node.dependencies:
                if dep in node_ids:
                    adj[dep].append(node.id)
                    in_degree[node.id] += 1

        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        visited = 0
        topo: list[str] = []
        while queue:
            current = queue.pop(0)
            visited += 1
            topo.append(current)
            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self.nodes):
            errors.append("Plan contains a dependency cycle")

        # 3. Every node must have non-empty expected_output and test_case
        for node in self.nodes:
            if not node.expected_output.strip():
                errors.append(f"Node '{node.id}' has empty expected_output")
            if not node.test_case.strip():
                errors.append(f"Node '{node.id}' has empty test_case")

        # 4. topo_order must match computed order if already set
        if self.topo_order and self.topo_order != topo:
            errors.append("topo_order does not match computed topological sort")

        return errors

    def compute_topo_order(self) -> list[str]:
        """Compute and return topological order. Does not mutate self."""
        in_degree = {n.id: 0 for n in self.nodes}
        adj = {n.id: [] for n in self.nodes}
        for node in self.nodes:
            for dep in node.dependencies:
                if dep in adj:
                    adj[dep].append(node.id)
                    in_degree[node.id] += 1

        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        topo: list[str] = []
        while queue:
            current = queue.pop(0)
            topo.append(current)
            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return topo

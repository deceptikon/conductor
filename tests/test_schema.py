"""Plan.validate() and compute_topo_order — the contract layer.

These tests exercise `conductor.schema` which *does* exist and should
already be GREEN. If any go RED, it means a regression in the schema
contract and the change must be reverted or the test updated in tandem.
"""
from __future__ import annotations

import pytest

from conductor.schema import Plan, TaskNode


# ---------------------------------------------------------------------------
#  Plan construction
# ---------------------------------------------------------------------------
def test_plan_construction_minimal():
    p = Plan(id="p", version=1, nodes=[TaskNode(id="a", description="d")])
    assert p.id == "p"
    assert p.version == 1
    assert p.node_map() == {"a": p.nodes[0]}


def test_plan_empty_nodes_validates_clean():
    """Edge case: a plan with no nodes is a valid (no-op) plan."""
    p = Plan(id="empty", version=1, nodes=[])
    assert p.validate() == []
    assert p.compute_topo_order() == []


# ---------------------------------------------------------------------------
#  validate() — dependency existence
# ---------------------------------------------------------------------------
def test_validate_missing_dependency():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", dependencies=["ghost"]),
        TaskNode(id="b", description="d", expected_output="x", test_case="x"),
    ])
    errs = p.validate()
    assert any("unknown node 'ghost'" in e for e in errs)


def test_validate_all_deps_present():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", expected_output="x", test_case="x"),
        TaskNode(id="b", description="d", dependencies=["a"],
                 expected_output="x", test_case="x"),
    ])
    assert p.validate() == []


# ---------------------------------------------------------------------------
#  validate() — cycle detection (Kahn's)
# ---------------------------------------------------------------------------
def test_validate_detects_cycle():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", dependencies=["c"],
                 expected_output="x", test_case="x"),
        TaskNode(id="b", description="d", dependencies=["a"],
                 expected_output="x", test_case="x"),
        TaskNode(id="c", description="d", dependencies=["b"],
                 expected_output="x", test_case="x"),
    ])
    assert any("cycle" in e for e in p.validate())


def test_validate_dag_no_cycle():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", dependencies=[],
                 expected_output="x", test_case="x"),
        TaskNode(id="b", description="d", dependencies=["a"],
                 expected_output="x", test_case="x"),
        TaskNode(id="c", description="d", dependencies=["a", "b"],
                 expected_output="x", test_case="x"),
    ])
    assert p.validate() == []


# ---------------------------------------------------------------------------
#  validate() — contract completeness
# ---------------------------------------------------------------------------
def test_validate_empty_expected_output():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", expected_output="", test_case="t"),
    ])
    assert any("empty expected_output" in e for e in p.validate())


def test_validate_empty_test_case():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", expected_output="x", test_case=""),
    ])
    assert any("empty test_case" in e for e in p.validate())


def test_validate_both_contracts_empty():
    """Empty contract on both fields → two separate errors."""
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", expected_output="", test_case=""),
    ])
    errs = p.validate()
    assert any("expected_output" in e for e in errs)
    assert any("test_case" in e for e in errs)


# ---------------------------------------------------------------------------
#  validate() — topo_order mismatch
# ---------------------------------------------------------------------------
def test_validate_topo_order_mismatch():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", dependencies=[],
                 expected_output="x", test_case="x"),
        TaskNode(id="b", description="d", dependencies=["a"],
                 expected_output="x", test_case="x"),
    ], topo_order=["b", "a"])  # wrong order
    assert any("topo_order" in e for e in p.validate())


def test_validate_topo_order_correct():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d", dependencies=[],
                 expected_output="x", test_case="x"),
        TaskNode(id="b", description="d", dependencies=["a"],
                 expected_output="x", test_case="x"),
    ], topo_order=["a", "b"])
    assert p.validate() == []


# ---------------------------------------------------------------------------
#  compute_topo_order()
# ---------------------------------------------------------------------------
def test_topo_order_linear_chain():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="a", description="d"),
        TaskNode(id="b", description="d", dependencies=["a"]),
        TaskNode(id="c", description="d", dependencies=["b"]),
    ])
    assert p.compute_topo_order() == ["a", "b", "c"]


def test_topo_order_fan_out():
    p = Plan(id="p", version=1, nodes=[
        TaskNode(id="root", description="d"),
        TaskNode(id="left", description="d", dependencies=["root"]),
        TaskNode(id="right", description="d", dependencies=["root"]),
        TaskNode(id="leaf", description="d", dependencies=["left", "right"]),
    ])
    order = p.compute_topo_order()
    assert order[0] == "root"
    assert order[-1] == "leaf"
    assert set(order[1:3]) == {"left", "right"}


# ---------------------------------------------------------------------------
#  node_map()
# ---------------------------------------------------------------------------
def test_node_map_by_id():
    a = TaskNode(id="a", description="d1")
    b = TaskNode(id="b", description="d2")
    p = Plan(id="p", version=1, nodes=[a, b])
    m = p.node_map()
    assert m["a"] is a
    assert m["b"] is b

from __future__ import annotations

from backend.application.resources.rollback_order import compute_rollback_order


def test_rollback_order_reverses_safe_start_order() -> None:
    start_order = ["gamma", "beta", "alpha"]
    rollback, error = compute_rollback_order(["alpha", "beta", "gamma"], full_start_order=start_order, dep_map={})
    assert error is None
    assert rollback == ["alpha", "beta", "gamma"]


def test_rollback_order_refuses_batch_cycle() -> None:
    dep_map = {"cycle_a": ["cycle_b"], "cycle_b": ["cycle_a"]}
    rollback, error = compute_rollback_order(["cycle_a", "cycle_b"], full_start_order=None, dep_map=dep_map)
    assert rollback is None
    assert "cycle" in (error or "").lower()

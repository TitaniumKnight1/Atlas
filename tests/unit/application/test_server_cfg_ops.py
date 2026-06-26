from __future__ import annotations

from backend.application.resources.server_cfg_ops import add_ensure_line, list_ensure_lines


def test_add_ensure_line_places_resource_after_dependencies() -> None:
    content = "ensure gamma\nensure alpha\n"
    updated, index = add_ensure_line(content, "beta", dependency_names=["gamma"])
    order = list_ensure_lines(updated)
    assert order.index("gamma") < order.index("beta")
    assert index == order.index("beta")
    assert "ensure alpha" in updated


def test_add_ensure_line_appends_when_dependency_not_present() -> None:
    content = "ensure alpha\n"
    updated, _ = add_ensure_line(content, "beta", dependency_names=["missing"])
    assert updated.endswith("ensure beta\n")
    assert list_ensure_lines(updated) == ["alpha", "beta"]

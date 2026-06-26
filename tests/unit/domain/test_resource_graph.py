from __future__ import annotations

from backend.domain.resources.graph import build_dependency_graph, detect_duplicate_resource_names
from backend.domain.resources.manifest_parser import normalize_dependency_name, parse_manifest
from backend.domain.resources.types import FindingType


def test_parse_fxmanifest_dependencies_and_provide() -> None:
    content = """
fx_version 'cerulean'
game 'gta5'
version '1.2.3'
dependencies {
  'ox_lib',
  'oxmysql:2.0.0'
}
provide 'my_virtual_resource'
"""
    parsed = parse_manifest(content, manifest_kind="fxmanifest.lua")
    assert parsed.fx_version == "cerulean"
    assert parsed.games == ["gta5"]
    assert parsed.version == "1.2.3"
    assert parsed.dependencies == ["ox_lib", "oxmysql"]
    assert parsed.provides == ["my_virtual_resource"]
    assert parsed.manifest_valid is True


def test_parse_legacy_resource_manifest() -> None:
    content = """
resource_manifest_version '44febabe-d386-4d18-afbe-5e627f4af937'
game 'gta5'
dependency 'mapmanager'
"""
    parsed = parse_manifest(content, manifest_kind="__resource.lua")
    assert parsed.fx_version == "44febabe-d386-4d18-afbe-5e627f4af937"
    assert parsed.dependencies == ["mapmanager"]


def test_normalize_dependency_strips_at_prefix_and_version() -> None:
    assert normalize_dependency_name("@ox_lib/init.lua") == "ox_lib"
    assert normalize_dependency_name("oxmysql:2.0.0") == "oxmysql"


def test_topological_order_for_acyclic_graph() -> None:
    snapshot = build_dependency_graph({"a": ["b"], "b": ["c"], "c": []})
    assert snapshot.is_healthy is True
    assert snapshot.topological_order is not None
    order = snapshot.topological_order
    assert order is not None
    assert order.index("c") < order.index("b") < order.index("a")


def test_cycle_detection_self_and_multi_node() -> None:
    self_cycle = build_dependency_graph({"solo": ["solo"]})
    assert any(item.finding_type == FindingType.CYCLE for item in self_cycle.findings)
    assert self_cycle.topological_order is None

    multi = build_dependency_graph({"a": ["b"], "b": ["c"], "c": ["a"]})
    cycle_findings = [item for item in multi.findings if item.finding_type == FindingType.CYCLE]
    assert cycle_findings
    assert set(cycle_findings[0].nodes) >= {"a", "b", "c"}


def test_missing_dependency_detection() -> None:
    snapshot = build_dependency_graph({"main": ["missing-lib"]})
    missing = [item for item in snapshot.findings if item.finding_type == FindingType.MISSING_DEPENDENCY]
    assert len(missing) == 1
    assert missing[0].nodes == ["main", "missing-lib"]


def test_duplicate_provide_conflict() -> None:
    snapshot = build_dependency_graph(
        {"a": [], "b": []},
        provides={"a": ["shared"], "b": ["shared"]},
    )
    conflicts = [item for item in snapshot.findings if item.finding_type == FindingType.DUPLICATE_PROVIDE]
    assert conflicts


def test_duplicate_name_detection() -> None:
    findings = detect_duplicate_resource_names(["chat", "chat", "mapmanager"])
    assert any(item.finding_type == FindingType.DUPLICATE_NAME for item in findings)


def test_graph_builder_dependents_and_dependencies_transitive() -> None:
    from backend.domain.resources.graph import DependencyGraphBuilder

    builder = DependencyGraphBuilder()
    builder.add_resource("a", ["b"])
    builder.add_resource("b", ["c"])
    builder.add_resource("c", [])
    snapshot = builder.analyze()
    assert snapshot.topological_order is not None
    assert builder.dependencies("a", transitive=True) == ["b", "c"]
    assert builder.dependents("c", transitive=True) == ["a", "b"]

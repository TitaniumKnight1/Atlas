from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from backend.domain.resources.types import (
    DependencyFinding,
    DependencyGraphSnapshot,
    DependencyType,
    FindingSeverity,
    FindingType,
    GraphEdge,
)


@dataclass(slots=True)
class DependencyGraphBuilder:
    nodes: set[str] = field(default_factory=set)
    edges: list[GraphEdge] = field(default_factory=list)
    provides: dict[str, list[str]] = field(default_factory=dict)
    findings: list[DependencyFinding] = field(default_factory=list)

    def add_resource(self, name: str, dependencies: list[str], provides: list[str] | None = None) -> None:
        self.nodes.add(name)
        for dependency in dependencies:
            self.edges.append(GraphEdge(source=name, target=dependency, dependency_type=DependencyType.REQUIRES.value))
        if provides:
            self.provides[name] = list(provides)

    def analyze(self) -> DependencyGraphSnapshot:
        self.findings.extend(self._detect_duplicate_names())
        self.findings.extend(self._detect_duplicate_provides())
        self.findings.extend(self._detect_missing_dependencies())
        cycles = self._detect_cycles()
        self.findings.extend(cycles)
        order, _ = self._topological_order()
        if cycles:
            order = None
        is_healthy = not any(item.severity == FindingSeverity.ERROR for item in self.findings)
        return DependencyGraphSnapshot(
            nodes=sorted(self.nodes),
            edges=list(self.edges),
            provides=dict(self.provides),
            findings=list(self.findings),
            topological_order=order,
            is_healthy=is_healthy,
        )

    def dependents(self, resource_name: str, *, transitive: bool = False) -> list[str]:
        adjacency = _reverse_adjacency(self.edges)
        if not transitive:
            return sorted(adjacency.get(resource_name, []))
        return sorted(_walk(resource_name, adjacency))

    def dependencies(self, resource_name: str, *, transitive: bool = False) -> list[str]:
        adjacency = _forward_adjacency(self.edges)
        if not transitive:
            return sorted(adjacency.get(resource_name, []))
        return sorted(_walk(resource_name, adjacency))

    def _detect_duplicate_names(self) -> list[DependencyFinding]:
        return []

    def _detect_duplicate_provides(self) -> list[DependencyFinding]:
        owner: dict[str, str] = {}
        findings: list[DependencyFinding] = []
        for resource, provided in self.provides.items():
            for name in provided:
                prior = owner.get(name)
                if prior is not None and prior != resource:
                    findings.append(
                        DependencyFinding(
                            finding_type=FindingType.DUPLICATE_PROVIDE,
                            severity=FindingSeverity.ERROR,
                            message=f"Resources '{prior}' and '{resource}' both provide '{name}'",
                            nodes=[prior, resource],
                            details={"provide_name": name},
                        )
                    )
                else:
                    owner[name] = resource
        return findings

    def _detect_missing_dependencies(self) -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        for edge in self.edges:
            if edge.target in self.nodes:
                continue
            findings.append(
                DependencyFinding(
                    finding_type=FindingType.MISSING_DEPENDENCY,
                    severity=FindingSeverity.ERROR,
                    message=f"Resource '{edge.source}' depends on missing resource '{edge.target}'",
                    nodes=[edge.source, edge.target],
                )
            )
        return findings

    def _detect_cycles(self) -> list[DependencyFinding]:
        adjacency = _forward_adjacency(self.edges)
        visited: set[str] = set()
        stack: set[str] = set()
        cycles: list[list[str]] = []

        def visit(node: str, path: list[str]) -> None:
            if node in stack:
                if node in path:
                    start = path.index(node)
                    cycles.append(path[start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for target in adjacency.get(node, []):
                if target not in self.nodes:
                    continue
                visit(target, path + [target])
            stack.remove(node)

        for node in sorted(self.nodes):
            visit(node, [node])

        findings: list[DependencyFinding] = []
        for cycle in cycles:
            normalized = _normalize_cycle(cycle)
            findings.append(
                DependencyFinding(
                    finding_type=FindingType.CYCLE,
                    severity=FindingSeverity.ERROR,
                    message=f"Dependency cycle detected: {' -> '.join(normalized)}",
                    nodes=normalized,
                )
            )
        return findings

    def _topological_order(self) -> tuple[list[str] | None, str | None]:
        adjacency = _forward_adjacency([edge for edge in self.edges if edge.target in self.nodes])
        indegree = {node: 0 for node in self.nodes}
        for source, targets in adjacency.items():
            for target in targets:
                indegree[target] += 1

        queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
        ordered: list[str] = []
        while queue:
            node = queue.popleft()
            ordered.append(node)
            for target in sorted(adjacency.get(node, [])):
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)

        if len(ordered) != len(self.nodes):
            return None, "graph contains cycles"
        return list(reversed(ordered)), None


def build_dependency_graph(resources: dict[str, list[str]], provides: dict[str, list[str]] | None = None) -> DependencyGraphSnapshot:
    builder = DependencyGraphBuilder()
    for name, dependencies in resources.items():
        builder.add_resource(name, dependencies, (provides or {}).get(name, []))
    return builder.analyze()


def detect_duplicate_resource_names(names: list[str]) -> list[DependencyFinding]:
    counts: dict[str, int] = defaultdict(int)
    for name in names:
        counts[name] += 1
    findings: list[DependencyFinding] = []
    for name, count in counts.items():
        if count <= 1:
            continue
        findings.append(
            DependencyFinding(
                finding_type=FindingType.DUPLICATE_NAME,
                severity=FindingSeverity.ERROR,
                message=f"Duplicate resource name '{name}' detected {count} times",
                nodes=[name],
                details={"count": count},
            )
        )
    return findings


def _forward_adjacency(edges: list[GraphEdge]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge.target)
    return adjacency


def _reverse_adjacency(edges: list[GraphEdge]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.target].append(edge.source)
    return adjacency


def _walk(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(adjacency.get(start, []))
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, []))
    return seen


def _normalize_cycle(cycle: list[str]) -> list[str]:
    if not cycle:
        return cycle
    if cycle[0] == cycle[-1]:
        cycle = cycle[:-1]
    if not cycle:
        return cycle
    rotations = [cycle[i:] + cycle[:i] for i in range(len(cycle))]
    return min(rotations)

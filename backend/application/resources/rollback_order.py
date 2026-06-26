from __future__ import annotations

from collections import defaultdict, deque

from backend.domain.resources.graph import _forward_adjacency
from backend.domain.resources.types import DependencyType, GraphEdge


def compute_rollback_order(
    batch_names: list[str],
    *,
    full_start_order: list[str] | None,
    dep_map: dict[str, list[str]],
) -> tuple[list[str] | None, str | None]:
    """Derive rollback order: dependents before dependencies (reverse of safe-start order)."""
    if not batch_names:
        return None, "rollback batch is empty"

    batch_set = set(batch_names)
    if full_start_order:
        filtered = [name for name in full_start_order if name in batch_set]
        for name in sorted(batch_names):
            if name not in filtered:
                filtered.append(name)
        return list(reversed(filtered)), None

    edges: list[GraphEdge] = []
    for source in batch_names:
        for target in dep_map.get(source, []):
            if target in batch_set:
                edges.append(GraphEdge(source=source, target=target, dependency_type=DependencyType.REQUIRES.value))

    adjacency = _forward_adjacency(edges)
    indegree = {name: 0 for name in batch_set}
    for source, targets in adjacency.items():
        for target in targets:
            indegree[target] += 1

    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    start_order: list[str] = []
    while queue:
        node = queue.popleft()
        start_order.append(node)
        for target in sorted(adjacency.get(node, [])):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(start_order) != len(batch_set):
        return None, "batch contains dependency cycle"

    return list(reversed(start_order)), None

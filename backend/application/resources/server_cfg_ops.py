from __future__ import annotations

import re

ENSURE_LINE = re.compile(r"^\s*(ensure|start)\s+([^\s#;]+)", re.IGNORECASE)


def add_ensure_line(content: str, resource_name: str, *, dependency_names: list[str]) -> tuple[str, int]:
    """Insert ensure line after the last ensure line of declared dependencies when present."""
    lines = content.splitlines(keepends=True)
    ensure_indices: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = ENSURE_LINE.match(line)
        if match is None:
            continue
        ensure_indices[match.group(2).strip().strip('"').strip("'")] = index

    if resource_name in ensure_indices:
        return content, ensure_indices[resource_name]

    insert_after = -1
    for dependency in dependency_names:
        if dependency in ensure_indices:
            insert_after = max(insert_after, ensure_indices[dependency])

    new_line = f"ensure {resource_name}\n"
    if insert_after >= 0:
        lines.insert(insert_after + 1, new_line)
        return "".join(lines), insert_after + 1
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    lines.append(new_line)
    return "".join(lines), len(lines) - 1


def remove_ensure_line(content: str, resource_name: str) -> str:
    kept: list[str] = []
    for line in content.splitlines(keepends=True):
        match = ENSURE_LINE.match(line)
        if match and match.group(2).strip().strip('"').strip("'") == resource_name:
            continue
        kept.append(line)
    return "".join(kept)


def list_ensure_lines(content: str) -> list[str]:
    names: list[str] = []
    for line in content.splitlines():
        match = ENSURE_LINE.match(line.strip())
        if match:
            names.append(match.group(2).strip().strip('"').strip("'"))
    return names

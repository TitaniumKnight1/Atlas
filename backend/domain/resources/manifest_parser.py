from __future__ import annotations

import re

from backend.domain.resources.types import ParsedManifest

STRING_VALUE = re.compile(r"""^[\s]*([A-Za-z_][\w]*)[\s]+['"]([^'"]+)['"]""", re.MULTILINE)
TABLE_BLOCK = re.compile(r"""^[\s]*([A-Za-z_][\w]*)[\s]*\{([^}]*)\}""", re.MULTILINE | re.DOTALL)
SINGLE_DEPENDENCY = re.compile(r"""^[\s]*dependency[\s]+['"]([^'"]+)['"]""", re.MULTILINE | re.IGNORECASE)
SINGLE_PROVIDE = re.compile(r"""^[\s]*provide[\s]+['"]([^'"]+)['"]""", re.MULTILINE | re.IGNORECASE)
TABLE_STRINGS = re.compile(r"""['"]([^'"]+)['"]""")


def parse_manifest(content: str, *, manifest_kind: str) -> ParsedManifest:
    errors: list[str] = []
    if not content.strip():
        return ParsedManifest(
            manifest_kind=manifest_kind,
            fx_version=None,
            games=[],
            version=None,
            dependencies=[],
            provides=[],
            manifest_valid=False,
            errors=["empty manifest"],
        )

    fx_version = _string_value(content, "fx_version")
    if fx_version is None and manifest_kind == "__resource.lua":
        fx_version = _string_value(content, "resource_manifest_version")

    games = _games(content)
    version = _string_value(content, "version")
    dependencies = _collect_dependencies(content)
    provides = _collect_provides(content)

    if fx_version is None:
        errors.append("missing fx_version (or resource_manifest_version for legacy manifests)")
    if not games:
        errors.append("missing game/games declaration")

    return ParsedManifest(
        manifest_kind=manifest_kind,
        fx_version=fx_version,
        games=games,
        version=version,
        dependencies=dependencies,
        provides=provides,
        manifest_valid=not errors,
        errors=errors,
    )


def normalize_dependency_name(value: str) -> str:
    token = value.strip()
    if token.startswith("@"):
        token = token[1:]
    token = token.split("/", 1)[0]
    token = token.split(":", 1)[0]
    return token.strip()


def _string_value(content: str, key: str) -> str | None:
    pattern = re.compile(rf"""^[\s]*{re.escape(key)}[\s]+['"]([^'"]+)['"]""", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(content)
    return match.group(1).strip() if match else None


def _games(content: str) -> list[str]:
    single = _string_value(content, "game")
    if single:
        return [single]
    for match in TABLE_BLOCK.finditer(content):
        if match.group(1).lower() != "games":
            continue
        return [item.strip() for item in TABLE_STRINGS.findall(match.group(2)) if item.strip()]
    return []


def _collect_dependencies(content: str) -> list[str]:
    values: list[str] = []
    for match in SINGLE_DEPENDENCY.finditer(content):
        values.append(normalize_dependency_name(match.group(1)))
    for match in TABLE_BLOCK.finditer(content):
        if match.group(1).lower() not in {"dependencies", "dependency"}:
            continue
        for item in TABLE_STRINGS.findall(match.group(2)):
            if item.strip():
                values.append(normalize_dependency_name(item))
    return _unique(values)


def _collect_provides(content: str) -> list[str]:
    values: list[str] = []
    for match in SINGLE_PROVIDE.finditer(content):
        values.append(match.group(1).strip())
    for match in TABLE_BLOCK.finditer(content):
        if match.group(1).lower() not in {"provides", "provide"}:
            continue
        for item in TABLE_STRINGS.findall(match.group(2)):
            if item.strip():
                values.append(item.strip())
    return _unique(values)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered

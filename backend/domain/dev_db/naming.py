from __future__ import annotations

import re

_DOCKER_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]+")
_MAX_NAME_LENGTH = 63


def sanitize_docker_name(value: str) -> str:
    cleaned = _DOCKER_NAME_PATTERN.sub("-", value.strip()).strip("-_.")
    if not cleaned:
        cleaned = "project"
    if len(cleaned) > _MAX_NAME_LENGTH:
        cleaned = cleaned[:_MAX_NAME_LENGTH].rstrip("-_.")
    return cleaned


def container_name_for_project(project_id: str) -> str:
    return sanitize_docker_name(f"atlas-dev-mysql-{project_id}")


def volume_name_for_project(project_id: str) -> str:
    return sanitize_docker_name(f"atlas-dev-mysql-{project_id}")

from __future__ import annotations

import hashlib
import re

from backend.domain.config import FindingSeverity, ValidationFinding


KNOWN_DIRECTIVES = {
    "endpoint_add_tcp",
    "endpoint_add_udp",
    "sv_licenseKey",
    "sv_hostname",
    "sv_maxclients",
    "sets",
    "set",
    "ensure",
    "start",
    "stop",
    "exec",
    "rcon_password",
    "sv_enforceGameBuild",
    "sv_scriptHookAllowed",
}

ENDPOINT_PATTERN = re.compile(r'^endpoint_add_(?:tcp|udp)\s+"[^"]+"\s*$', re.IGNORECASE)
LICENSE_PATTERN = re.compile(r'^sv_licenseKey\s+"[^"]+"\s*$', re.IGNORECASE)
SET_PATTERN = re.compile(r'^(?:set|sets)\s+\S+\s+".*"\s*$', re.IGNORECASE)
RESOURCE_PATTERN = re.compile(r'^(?:ensure|start|stop)\s+\S+\s*$', re.IGNORECASE)
COMMENT_OR_EMPTY = re.compile(r"^\s*(#|//|;).*$|^\s*$")


class FiveMConfigValidator:
    """Local FiveM server.cfg validation rules (Cfx.re vanilla server.cfg conventions)."""

    def validate(self, *, path: str, content: str, config_type: str) -> list[ValidationFinding]:
        if config_type != "server_cfg":
            return []
        findings: list[ValidationFinding] = []
        lines = content.splitlines()
        has_license = False
        tcp_endpoints: list[int] = []
        udp_endpoints: list[int] = []
        seen_directives: dict[str, int] = {}

        for index, raw in enumerate(lines, start=1):
            line = raw.strip()
            if COMMENT_OR_EMPTY.match(line):
                continue
            if LICENSE_PATTERN.match(line):
                has_license = True
                if 'CHANGE_ME' in line.upper() or 'licenseKeyGoesHere' in line:
                    findings.append(
                        ValidationFinding(
                            rule_id="placeholder_license_key",
                            severity=FindingSeverity.WARNING,
                            message="sv_licenseKey appears to use a placeholder value",
                            path=path,
                            line=index,
                        )
                    )
                continue
            if line.lower().startswith("endpoint_add_tcp"):
                if not ENDPOINT_PATTERN.match(line):
                    findings.append(
                        ValidationFinding(
                            rule_id="malformed_endpoint_tcp",
                            severity=FindingSeverity.ERROR,
                            message="Malformed endpoint_add_tcp directive; expected endpoint_add_tcp \"host:port\"",
                            path=path,
                            line=index,
                        )
                    )
                else:
                    port = _extract_port(line)
                    if port is not None:
                        tcp_endpoints.append(port)
                continue
            if line.lower().startswith("endpoint_add_udp"):
                if not ENDPOINT_PATTERN.match(line):
                    findings.append(
                        ValidationFinding(
                            rule_id="malformed_endpoint_udp",
                            severity=FindingSeverity.ERROR,
                            message="Malformed endpoint_add_udp directive; expected endpoint_add_udp \"host:port\"",
                            path=path,
                            line=index,
                        )
                    )
                else:
                    port = _extract_port(line)
                    if port is not None:
                        udp_endpoints.append(port)
                continue
            if SET_PATTERN.match(line) or RESOURCE_PATTERN.match(line):
                directive = line.split()[0].lower()
                seen_directives[directive] = seen_directives.get(directive, 0) + 1
                continue
            token = line.split()[0] if line.split() else ""
            if token and token not in KNOWN_DIRECTIVES and not token.startswith("#"):
                findings.append(
                    ValidationFinding(
                        rule_id="unknown_directive",
                        severity=FindingSeverity.WARNING,
                        message=f"Unrecognized or non-standard directive: {token}",
                        path=path,
                        line=index,
                    )
                )

        if not has_license:
            findings.append(
                ValidationFinding(
                    rule_id="missing_license_key",
                    severity=FindingSeverity.ERROR,
                    message="server.cfg is missing sv_licenseKey (required for public FiveM servers per Cfx.re docs)",
                    path=path,
                )
            )
        if not tcp_endpoints and not udp_endpoints:
            findings.append(
                ValidationFinding(
                    rule_id="missing_endpoints",
                    severity=FindingSeverity.WARNING,
                    message="No endpoint_add_tcp or endpoint_add_udp directives found",
                    path=path,
                )
            )
        if tcp_endpoints and udp_endpoints and set(tcp_endpoints) != set(udp_endpoints):
            findings.append(
                ValidationFinding(
                    rule_id="endpoint_port_mismatch",
                    severity=FindingSeverity.WARNING,
                    message="TCP and UDP endpoint ports differ; FiveM commonly uses matching ports",
                    path=path,
                    details={"tcp_ports": tcp_endpoints, "udp_ports": udp_endpoints},
                )
            )
        duplicate_ports = [port for port in tcp_endpoints if tcp_endpoints.count(port) > 1]
        if duplicate_ports:
            findings.append(
                ValidationFinding(
                    rule_id="duplicate_tcp_endpoint",
                    severity=FindingSeverity.WARNING,
                    message="Duplicate endpoint_add_tcp port declarations detected",
                    path=path,
                    details={"ports": sorted(set(duplicate_ports))},
                )
            )
        return findings


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def unified_diff(old: str, new: str, path: str) -> str:
    import difflib

    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"{path} (current)", tofile=f"{path} (proposed)"))


def _extract_port(line: str) -> int | None:
    match = re.search(r":(\d+)", line)
    if not match:
        return None
    return int(match.group(1))

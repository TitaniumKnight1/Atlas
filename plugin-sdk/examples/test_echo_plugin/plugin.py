"""Minimal M9b test plugin — exercises IPC capability mediation only."""


def run(client, mode: str = "normal") -> None:
    if mode == "hang":
        import time

        time.sleep(3600)
        return
    if mode == "crash":
        raise RuntimeError("deliberate plugin crash for isolation test")
    if mode.startswith("contribution:"):
        _run_contribution(client, mode)
        return
    client.request_capability("read-config", {})
    client.request_capability("read-incidents", {})
    if mode == "mutate":
        client.request_capability(
            "filesystem-write",
            {"relative_path": "plugin-marker.txt", "content": "plugin-mediated-write\n", "idempotency_key": "plugin:mutate:1"},
        )


def _run_contribution(client, mode: str) -> None:
    _, point, identifier = mode.split(":", 2)
    if identifier.endswith(".crash"):
        raise RuntimeError("deliberate contribution crash")
    if point == "config-validators":
        response = client.request_capability("read-config", {})
        client.request_capability("read-incidents", {})
        config_count = len(response.get("result", {}).get("config_files", [])) if response.get("granted") else 0
        client.contribution_result(identifier, {"findings": [{"severity": "info", "message": f"config files visible: {config_count}"}]})
        return
    if point == "automation-actions":
        response = client.request_capability(
            "invoke-resource-lifecycle",
            {
                "relative_path": "plugin-contribution-marker.txt",
                "content": "plugin contribution mutation\n",
                "idempotency_key": "plugin:contribution:mutate:1",
            },
        )
        client.contribution_result(identifier, {"mutation": response})
        return
    if point == "commands":
        response = client.request_capability("read-project-metadata", {})
        project_name = response.get("result", {}).get("project", {}).get("name", "unknown")
        client.contribution_result(identifier, {"output": f"plugin command for {project_name}"})

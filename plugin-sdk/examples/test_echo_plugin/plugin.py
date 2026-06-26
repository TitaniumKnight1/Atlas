"""Minimal M9b test plugin — exercises IPC capability mediation only."""


def run(client, mode: str = "normal") -> None:
    if mode == "hang":
        import time

        time.sleep(3600)
        return
    if mode == "crash":
        raise RuntimeError("deliberate plugin crash for isolation test")
    client.request_capability("read-config", {})
    client.request_capability("read-incidents", {})
    if mode == "mutate":
        client.request_capability(
            "filesystem-write",
            {"relative_path": "plugin-marker.txt", "content": "plugin-mediated-write\n", "idempotency_key": "plugin:mutate:1"},
        )

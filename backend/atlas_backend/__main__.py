from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
from pathlib import Path

import uvicorn

from backend.atlas_backend.app import create_app


READY_EVENT = "atlas.backend.ready"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the embedded Atlas FastAPI backend.")
    parser.add_argument("--app-data-dir", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=0, type=int)
    args = parser.parse_args()

    asyncio.run(run_server(args.app_data_dir, args.host, args.port))


async def run_server(app_data_dir: Path, host: str, port: int) -> None:
    socket_ = _bind_socket(host, port)
    actual_host, actual_port = socket_.getsockname()[:2]
    app = create_app(app_data_dir=app_data_dir)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=actual_host,
            port=actual_port,
            lifespan="on",
            log_level="info",
            access_log=False,
        )
    )

    server_task = asyncio.create_task(server.serve(sockets=[socket_]))
    while not server.started and not server.should_exit:
        if server_task.done():
            await server_task
            raise RuntimeError("Uvicorn exited before backend readiness")
        await asyncio.sleep(0.02)

    if server.should_exit:
        raise RuntimeError("Uvicorn requested shutdown before backend readiness")

    print(
        json.dumps({"event": READY_EVENT, "host": actual_host, "port": actual_port}),
        flush=True,
    )

    stdin_task = asyncio.create_task(_wait_for_shutdown(server))
    try:
        await server_task
    finally:
        stdin_task.cancel()


def _bind_socket(host: str, port: int) -> socket.socket:
    socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_.bind((host, port))
    socket_.listen(128)
    return socket_


async def _wait_for_shutdown(server: uvicorn.Server) -> None:
    loop = asyncio.get_running_loop()
    while not server.should_exit:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line == "":
            # Parent process closed stdin (normal exit, force-close, or job teardown).
            server.should_exit = True
            return
        if line.strip().lower() == "shutdown":
            server.should_exit = True
            return


if __name__ == "__main__":
    main()

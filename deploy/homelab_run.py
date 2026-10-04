"""Run the existing native workers under one homelab systemd lifecycle.

No trading/auth logic is implemented here. A worker exit fails the whole unit;
systemd and homelab retain restart, release activation and rollback ownership.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen


@dataclass(frozen=True)
class Worker:
    name: str
    command: list[str]
    health_url: str


def port(variable: str, default: int) -> int:
    value = int(os.environ.get(variable, default))
    if not 1024 <= value <= 65535:
        raise ValueError(f"{variable} must be an unprivileged port")
    return value


def worker_specs() -> list[Worker]:
    if os.environ.get("MARKET_DATA_HTTP_HOST", "127.0.0.1") != "127.0.0.1":
        raise ValueError("native market listener must use loopback 127.0.0.1")
    market = port("MARKET_DATA_HTTP_PORT", 8110)
    trading = port("TRADING_HTTP_PORT", 8111)
    auth = port("AUTH_HTTP_PORT", 8112)
    health = port("HOMELAB_HEALTH_PORT", 8113)
    if len({market, trading, auth, health}) != 4:
        raise ValueError("native worker and health ports must be distinct")

    def api(module: str, listen: int) -> list[str]:
        return [
            sys.executable,
            "-m",
            "uvicorn",
            module,
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(listen),
            "--workers",
            "1",
            "--proxy-headers",
            "--forwarded-allow-ips",
            "127.0.0.1",
        ]

    return [
        Worker(
            "auth",
            api("auth.server:create_default_app", auth),
            f"http://127.0.0.1:{auth}/auth/session",
        ),
        Worker(
            "market",
            [sys.executable, "-m", "market_data.app"],
            f"http://127.0.0.1:{market}/health",
        ),
        Worker(
            "trading",
            api("trading.app:create_default_app", trading),
            f"http://127.0.0.1:{trading}/health",
        ),
    ]


def ready(workers: list[Worker], processes: list[subprocess.Popen[bytes]]) -> bool:
    if len(processes) != len(workers) or any(p.poll() is not None for p in processes):
        return False
    for worker in workers:
        try:
            with urlopen(worker.health_url, timeout=0.5) as response:
                if response.status != 200:
                    return False
                if worker.name == "market":
                    payload = json.loads(response.read())
                    instruments = payload.get("instruments", {})
                    if not instruments or not all(
                        v.get("last_tick") for v in instruments.values()
                    ):
                        return False
        except HTTPError as error:
            if worker.name != "auth" or error.code != 401:
                return False
        except (OSError, ValueError, TypeError):
            return False
    return True


def monitor(processes: list[subprocess.Popen[bytes]], stop: threading.Event) -> int:
    while not stop.is_set():
        if any(process.poll() is not None for process in processes):
            return 1  # Even an unexpected clean worker exit is a project failure.
        stop.wait(0.2)
    return 0


def stop_children(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    # market_data.app has a non-loopback development default; set it explicitly.
    os.environ.setdefault("MARKET_DATA_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("MARKET_DATA_HTTP_PORT", "8110")
    workers = worker_specs()
    processes: list[subprocess.Popen[bytes]] = []
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            healthy = ready(workers, processes)
            body = json.dumps({"status": "ok" if healthy else "unavailable"}).encode()
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    server: HTTPServer | None = None
    thread: threading.Thread | None = None
    try:
        for worker in workers:
            processes.append(subprocess.Popen(worker.command))
        server = HTTPServer(
            ("127.0.0.1", port("HOMELAB_HEALTH_PORT", 8113)), HealthHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return monitor(processes, stop)
    finally:
        if server is not None:
            if thread is not None:
                server.shutdown()
                thread.join()
            server.server_close()
        stop_children(processes)


if __name__ == "__main__":
    raise SystemExit(main())

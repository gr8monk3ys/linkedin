"""Smoke test the Reflex web app by starting it and probing its routes."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from linkedin.web.app import REGISTERED_ROUTES

REPO_ROOT = Path(__file__).resolve().parents[3]
STARTUP_TIMEOUT_SECONDS = 180
ROUTE_TIMEOUT_SECONDS = 60
SHUTDOWN_TIMEOUT_SECONDS = 15


def reserve_port() -> int:
    """Ask the OS for an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, timeout_seconds: int) -> None:
    """Wait until a local TCP port starts accepting connections."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"Timed out waiting for port {port} to accept connections.")


def wait_for_route(base_url: str, route: str, timeout_seconds: int) -> None:
    """Wait until an HTTP route returns 200."""
    url = f"{base_url}{route}"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200:
                    return
                last_error = RuntimeError(f"{url} returned {response.status}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url} to return 200. Last error: {last_error}")


def build_command(frontend_port: int, backend_port: int) -> list[str]:
    """Build the startup command for the installed web app."""
    cli_path = shutil.which("linkedin-web")
    if cli_path:
        return [cli_path, "--frontend-port", str(frontend_port), "--backend-port", str(backend_port)]
    return [sys.executable, "-m", "reflex", "run", "--frontend-port", str(frontend_port), "--backend-port", str(backend_port)]


def print_failure_logs(log_path: Path) -> None:
    """Emit recent server logs to help diagnose startup failures in CI."""
    if not log_path.exists():
        return
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = "\n".join(lines[-200:])
    if tail:
        print("Recent server log output:", file=sys.stderr)
        print(tail, file=sys.stderr)


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate the server and any children it spawned."""
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.5)
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def main() -> int:
    """Run the smoke test."""
    frontend_port = reserve_port()
    backend_port = reserve_port()
    base_url = f"http://127.0.0.1:{frontend_port}"
    log_dir = Path(tempfile.mkdtemp(prefix="linkedin-web-smoke-"))
    log_path = log_dir / "server.log"
    env = os.environ.copy()
    env.setdefault("REFLEX_DIR", str(log_dir / "reflex"))
    command = build_command(frontend_port, backend_port)

    print(f"Starting LinkedIn web app on frontend {frontend_port} / backend {backend_port}")

    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        try:
            wait_for_port(frontend_port, STARTUP_TIMEOUT_SECONDS)
            wait_for_port(backend_port, STARTUP_TIMEOUT_SECONDS)
            for route in REGISTERED_ROUTES:
                wait_for_route(base_url, route, ROUTE_TIMEOUT_SECONDS)
                print(f"Verified {route}")
        except Exception:
            print_failure_logs(log_path)
            raise
        finally:
            stop_process_group(process)

    print("Web smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

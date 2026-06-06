import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
HOST = "127.0.0.1"
DEFAULT_PORT = 8501
LOCAL_HTTP = build_opener(ProxyHandler({}))


def log_paths(port: int) -> tuple[Path, Path]:
    return ROOT / f"streamlit-{port}.out.log", ROOT / f"streamlit-{port}.err.log"


def pid_path(port: int) -> Path:
    return ROOT / f"streamlit-{port}.pid"


def streamlit_command(port: int) -> list[str]:
    return [
        PYTHON,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "app.py"),
        "--server.headless=true",
        f"--server.address={HOST}",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]


def url(port: int) -> str:
    return f"http://{HOST}:{port}/"


def port_accepts_connections(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=1.0):
            return True
    except OSError:
        return False


def app_ready(port: int) -> bool:
    try:
        with LOCAL_HTTP.open(url(port), timeout=2.0) as response:
            return 200 <= response.status < 500
    except HTTPError as exc:
        return 200 <= exc.code < 500
    except URLError:
        return False
    except OSError:
        return False


def wait_until_ready(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if app_ready(port):
            return True
        time.sleep(0.5)
    return False


def read_pid(port: int) -> int | None:
    path = pid_path(port)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def process_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(
            process_query_limited_information | synchronize,
            False,
            int(pid),
        )
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def creation_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    )


def start_detached(port: int) -> int:
    if app_ready(port):
        print(f"Streamlit already running: {url(port)}")
        return 0

    out_log, err_log = log_paths(port)
    out_log.parent.mkdir(parents=True, exist_ok=True)

    with out_log.open("ab", buffering=0) as stdout, err_log.open("ab", buffering=0) as stderr:
        kwargs = {
            "cwd": ROOT,
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": stderr,
            "close_fds": True,
        }
        flags = creation_flags()
        if flags:
            kwargs["creationflags"] = flags
        try:
            process = subprocess.Popen(streamlit_command(port), **kwargs)
        except OSError:
            kwargs.pop("creationflags", None)
            process = subprocess.Popen(streamlit_command(port), **kwargs)

    pid_path(port).write_text(str(process.pid), encoding="utf-8")
    if wait_until_ready(port):
        print(f"Streamlit started: {url(port)} pid={process.pid}")
        return 0

    print(f"Streamlit did not become ready within 30s. Check {err_log.name}.")
    return 1


def stop_server(port: int) -> int:
    pid = read_pid(port)
    if pid is None:
        print(f"No pid file found for port {port}.")
        return 0
    if not process_running(pid):
        pid_path(port).unlink(missing_ok=True)
        print(f"Stale pid file removed for port {port}.")
        return 0

    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        os.kill(pid, 15)
    pid_path(port).unlink(missing_ok=True)
    print(f"Stopped Streamlit pid={pid}.")
    return 0


def status(port: int) -> int:
    pid = read_pid(port)
    pid_state = "unknown"
    if pid is not None:
        pid_state = "running" if process_running(pid) else "stale"
    print(f"url={url(port)}")
    print(f"pid={pid if pid is not None else '-'} ({pid_state})")
    print(f"tcp={'open' if port_accepts_connections(port) else 'closed'}")
    print(f"http={'ready' if app_ready(port) else 'not-ready'}")
    return 0


def serve_foreground(port: int) -> int:
    out_log, err_log = log_paths(port)
    with out_log.open("ab", buffering=0) as stdout, err_log.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            streamlit_command(port),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        pid_path(port).write_text(str(process.pid), encoding="utf-8")
        try:
            while process.poll() is None:
                time.sleep(10)
        finally:
            pid_path(port).unlink(missing_ok=True)
    return int(process.returncode or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the local Streamlit preview server.")
    parser.add_argument("command", nargs="?", choices=["serve", "start", "stop", "status"], default="serve")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "start":
        return start_detached(args.port)
    if args.command == "stop":
        return stop_server(args.port)
    if args.command == "status":
        return status(args.port)
    return serve_foreground(args.port)


if __name__ == "__main__":
    raise SystemExit(main())

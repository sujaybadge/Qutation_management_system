"""
Launch the Django web app inside a desktop window using pywebview.

Usage (from repo root):
    python desktop_launcher.py

It starts the Django development server on 127.0.0.1:8000 in the background
and opens a native window that points to it. Adjust PORT or TITLE below if needed.
"""
import os
import socket
import subprocess
import sys
import time

import webview

HOST = "127.0.0.1"
PORT = int(os.environ.get("QUOTATION_PORT", "8000"))
TITLE = "Quotation Studio"


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _wait_for_server(timeout: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.8):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _start_server():
    env = os.environ.copy()
    cmd = [sys.executable, "manage.py", "runserver", "--noreload", "--insecure", f"{HOST}:{PORT}"]
    # Inherit stdout/stderr so you can see server logs if something fails
    return subprocess.Popen(cmd, env=env)


def main():
    server_proc = None
    try:
        if not _port_available(HOST, PORT):
            print(f"Port {PORT} is busy; assuming server already running.")
        else:
            print(f"Starting Django server at http://{HOST}:{PORT} ...")
            server_proc = _start_server()

        if not _wait_for_server():
            print("Server did not start in time. Check console output for errors.", file=sys.stderr)
            if server_proc:
                server_proc.terminate()
            sys.exit(1)

        # Launch desktop window
        webview.create_window(TITLE, f"http://{HOST}:{PORT}", width=1200, height=800)
        webview.start()
    finally:
        if server_proc:
            server_proc.terminate()


if __name__ == "__main__":
    main()

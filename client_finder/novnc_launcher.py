"""noVNC launcher for Docker browser-based login.

Starts Xvfb (virtual display) + fluxbox (window manager) + websockify +
noVNC, then launches Chromium. The user connects via their web browser to
the noVNC URL to complete manual login + 2FA. Cookies are saved after
login, and subsequent runs use headless Chromium with those cookies.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


class NovncLauncher:
    """Manages Xvfb + noVNC + Chromium for manual browser login in Docker."""

    def __init__(
        self,
        vnc_port: int = 5900,
        websockify_port: int = 6080,
        novnc_path: str = "/usr/share/novnc",
        display: str = ":99",
        screen_resolution: str = "1366x768x24",
        login_timeout_seconds: int = 600,
    ):
        self.vnc_port = vnc_port
        self.websockify_port = websockify_port
        self.novnc_path = novnc_path
        self.display = display
        self.screen_resolution = screen_resolution
        self.login_timeout_seconds = login_timeout_seconds

        self._xvfb_proc: subprocess.Popen | None = None
        self._fluxbox_proc: subprocess.Popen | None = None
        self._websockify_proc: subprocess.Popen | None = None
        self._chromium_proc: subprocess.Popen | None = None
        self._novnc_url: str | None = None

    @property
    def novnc_url(self) -> str | None:
        return self._novnc_url

    def start(self, login_url: str = "https://mail.google.com") -> str:
        """Start the full noVNC stack and return the noVNC URL for the user."""
        os.environ["DISPLAY"] = self.display

        # 1. Start Xvfb
        self._xvfb_proc = subprocess.Popen(
            [
                "Xvfb",
                self.display,
                "-screen",
                "0",
                self.screen_resolution,
                "-nolisten",
                "tcp",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        # 2. Start fluxbox window manager
        self._fluxbox_proc = subprocess.Popen(
            ["fluxbox"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": self.display},
        )
        time.sleep(1)

        # 3. Start websockify (VNC to WebSocket proxy)
        self._websockify_proc = subprocess.Popen(
            [
                "websockify",
                str(self.vnc_port),
                "--web",
                self.novnc_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        # 4. Build noVNC URL
        host = os.environ.get("NOVNC_HOST", "localhost")
        self._novnc_url = (
            f"http://{host}:{self.websockify_port}/vnc.html?"
            f"autoconnect=1&resize=remote&reconnect=1"
        )

        # 5. Launch Chromium pointing at Xvfb display
        self._chromium_proc = subprocess.Popen(
            [
                "chromium-browser",
                f"--display={self.display}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--user-data-dir=/tmp/chromium-novnc-profile",
                login_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": self.display},
        )

        print(f"\n{'='*70}")
        print(f"noVNC is ready!")
        print(f"Open this URL in your browser: {self._novnc_url}")
        print(f"Log in to {login_url} and complete any 2FA.")
        print(f"Press Enter here after you've logged in.")
        print(f"{'='*70}\n")

        return self._novnc_url

    def wait_for_login(self, message: str | None = None) -> bool:
        """Wait for the user to press Enter after completing login."""
        if message:
            print(message)
        else:
            print("Waiting for you to complete login in the browser...")
        try:
            input("Press Enter after login is complete: ")
            return True
        except (EOFError, KeyboardInterrupt):
            return False

    def stop(self) -> None:
        """Stop all processes."""
        for proc in [self._chromium_proc, self._websockify_proc, self._fluxbox_proc, self._xvfb_proc]:
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._xvfb_proc = None
        self._fluxbox_proc = None
        self._websockify_proc = None
        self._chromium_proc = None


def check_novnc_available() -> bool:
    """Check if noVNC and Xvfb are available on this system."""
    from shutil import which
    return bool(which("Xvfb") and which("websockify") and Path("/usr/share/novnc/vnc.html").exists())


def is_docker() -> bool:
    """Check if running inside a Docker container."""
    return Path("/.dockerenv").exists() or Path("/proc/1/cgroup").read_text(errors="ignore").find("docker") != -1
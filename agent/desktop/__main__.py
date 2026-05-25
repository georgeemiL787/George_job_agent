"""Launch the native desktop app."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _fix_cwd() -> None:
    r"""When running as a PyInstaller bundle the working directory is
    unpredictable (e.g. C:\Windows\System32 when double-clicked from
    Explorer).  pydantic-settings reads .env relative to CWD, and
    config_io.py writes .env to Path('.env'), so we anchor CWD to the
    directory that contains the frozen executable."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        os.chdir(exe_dir)


_fix_cwd()

from agent.desktop import run_desktop  # noqa: E402 – must come after chdir

if __name__ == "__main__":
    raise SystemExit(run_desktop(sys.argv))

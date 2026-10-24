"""
Create "AirMouse" shortcuts on the Desktop and in the Start menu (Windows).

They start AirMouse with pythonw.exe — no terminal window — from this folder.
Run once, with the project's Python:

    .\.venv\Scripts\python tools\create_shortcuts.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from core.icon import save_ico  # noqa: E402


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    if sys.platform != "win32":
        print("Shortcuts are only created on Windows.")
        return 1
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        print(f"pythonw.exe not found next to {sys.executable}")
        return 1
    icon = save_ico(APP_DIR / "assets" / "airmouse.ico")

    script = "\n".join(
        [
            "$shell = New-Object -ComObject WScript.Shell",
            "foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {",
            "  $s = $shell.CreateShortcut((Join-Path $folder 'AirMouse.lnk'))",
            f"  $s.TargetPath = {_ps_quote(str(pythonw))}",
            f"  $s.Arguments = {_ps_quote(chr(34) + str(APP_DIR / 'main.py') + chr(34))}",
            f"  $s.WorkingDirectory = {_ps_quote(str(APP_DIR))}",
            f"  $s.IconLocation = {_ps_quote(str(icon))}",
            "  $s.Description = 'AirMouse - control the mouse with your hands'",
            "  $s.Save()",
            "  Write-Output (Join-Path $folder 'AirMouse.lnk')",
            "}",
        ]
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip())
        return result.returncode
    print("Shortcuts created:")
    print(result.stdout.strip())
    print("Open AirMouse from the Desktop or the Start menu. Its icon appears next to the clock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

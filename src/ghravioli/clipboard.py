"""Platform clipboard adapters for Grasshopper archive text."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable


class ClipboardError(RuntimeError):
    """The selected clipboard command failed."""


class ClipboardUnavailable(ClipboardError):
    """No supported clipboard command is available."""


Runner = Callable[..., subprocess.CompletedProcess[bytes]]
Which = Callable[[str], str | None]


POWERSHELL_CLIPBOARD_SCRIPT = (
    "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false); "
    "$text = [Console]::In.ReadToEnd(); "
    "Set-Clipboard -Value $text"
)


def copy_to_clipboard(
    data: bytes,
    *,
    platform: str = sys.platform,
    which: Which = shutil.which,
    runner: Runner = subprocess.run,
) -> str:
    """Copy archive bytes as text and return the adapter name used."""

    adapter, command = _select_adapter(platform, which)
    result = runner(command, input=data, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        message = detail or f"{adapter} exited with status {result.returncode}"
        raise ClipboardError(message)
    return adapter


def _select_adapter(platform: str, which: Which) -> tuple[str, list[str]]:
    if platform == "darwin":
        executable = which("pbcopy")
        if executable:
            return "pbcopy", [executable]
    elif platform.startswith("win"):
        for name, adapter in (
            ("pwsh.exe", "pwsh"),
            ("pwsh", "pwsh"),
            ("powershell.exe", "powershell"),
            ("powershell", "powershell"),
        ):
            executable = which(name)
            if executable:
                return adapter, [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    POWERSHELL_CLIPBOARD_SCRIPT,
                ]
    elif platform.startswith("linux"):
        wayland = which("wl-copy")
        if wayland:
            return "wl-copy", [wayland, "--type", "text/plain"]
        xclip = which("xclip")
        if xclip:
            return "xclip", [xclip, "-selection", "clipboard"]
    raise ClipboardUnavailable(f"no supported clipboard command is available for {platform}")

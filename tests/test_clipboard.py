from __future__ import annotations

import subprocess
import unittest

from ghravioli.clipboard import ClipboardError, ClipboardUnavailable, copy_to_clipboard


class ClipboardTestCase(unittest.TestCase):
    def test_macos_passes_exact_archive_bytes_to_pbcopy(self) -> None:
        calls: list[tuple[list[str], bytes]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append((command, kwargs["input"]))
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        adapter = copy_to_clipboard(
            b"<Archive />",
            platform="darwin",
            which=lambda name: "/usr/bin/pbcopy" if name == "pbcopy" else None,
            runner=runner,
        )

        self.assertEqual(adapter, "pbcopy")
        self.assertEqual(calls, [(["/usr/bin/pbcopy"], b"<Archive />")])

    def test_selects_available_windows_and_linux_adapters(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        windows = copy_to_clipboard(
            b"xml",
            platform="win32",
            which=lambda name: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            if name == "powershell.exe"
            else None,
            runner=runner,
        )
        linux = copy_to_clipboard(
            b"xml",
            platform="linux",
            which=lambda name: "/usr/bin/wl-copy" if name == "wl-copy" else None,
            runner=runner,
        )

        self.assertEqual(windows, "powershell")
        self.assertEqual(linux, "wl-copy")
        self.assertEqual(commands[1], ["/usr/bin/wl-copy", "--type", "text/plain"])

    def test_windows_prefers_pwsh_and_reads_one_utf8_string(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        locations = {
            "pwsh.exe": "C:/Program Files/PowerShell/7/pwsh.exe",
            "powershell.exe": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        }
        adapter = copy_to_clipboard(
            "café\n東京".encode(),
            platform="win32",
            which=locations.get,
            runner=runner,
        )

        self.assertEqual(adapter, "pwsh")
        self.assertEqual(commands[0][0], locations["pwsh.exe"])
        script = commands[0][-1]
        self.assertIn("UTF8Encoding($false)", script)
        self.assertIn("Console]::In.ReadToEnd()", script)
        self.assertIn("Set-Clipboard -Value $text", script)
        self.assertNotIn("$input |", script)

    def test_unavailable_platform_does_not_start_a_process(self) -> None:
        called = False

        def runner(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            nonlocal called
            called = True
            raise AssertionError("runner must not be called")

        with self.assertRaisesRegex(ClipboardUnavailable, "no supported clipboard command"):
            copy_to_clipboard(
                b"xml",
                platform="linux",
                which=lambda _name: None,
                runner=runner,
            )
        self.assertFalse(called)

    def test_command_failure_reports_stderr(self) -> None:
        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(command, 7, stdout=b"", stderr=b"clipboard locked")

        with self.assertRaisesRegex(ClipboardError, "clipboard locked"):
            copy_to_clipboard(
                b"xml",
                platform="darwin",
                which=lambda _name: "/usr/bin/pbcopy",
                runner=runner,
            )


if __name__ == "__main__":
    unittest.main()

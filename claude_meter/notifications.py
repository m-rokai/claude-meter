"""macOS notification support."""

import subprocess


def notify(title: str, message: str, sound: bool = True):
    """Send a macOS notification via osascript."""
    sound_part = 'sound name "Funk"' if sound else ""
    script = (
        f'display notification "{_escape(message)}" '
        f'with title "{_escape(title)}" {sound_part}'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _escape(text: str) -> str:
    return text.replace('"', '\\"').replace("\\", "\\\\")

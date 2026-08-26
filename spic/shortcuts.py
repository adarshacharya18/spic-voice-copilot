"""Helper for registering GNOME global shortcuts via gsettings."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("spic.shortcuts")


def register_gnome_shortcuts(python_bin: str, spic_entrypoint: str) -> bool:
    """Register custom GNOME shortcuts for Spic Fast and Smart triggers."""
    try:
        # Check if gsettings is available
        res = subprocess.run(["which", "gsettings"], capture_output=True, text=True)
        if res.returncode != 0:
            print("[Spic] gsettings not found. Manual shortcut configuration required.")
            return False

        # Read existing custom keybindings
        cmd_get = ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"]
        result = subprocess.run(cmd_get, capture_output=True, text=True, check=True)
        current_val = result.stdout.strip()

        # Parse array of paths
        paths = []
        if current_val.startswith("[") and current_val.endswith("]"):
            raw_paths = current_val[1:-1].split(",")
            paths = [p.strip().strip("'").strip('"') for p in raw_paths if p.strip()]

        fast_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-fast/"
        smart_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-smart/"

        if fast_path not in paths:
            paths.append(fast_path)
        if smart_path not in paths:
            paths.append(smart_path)

        # Set array back
        array_str = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
        subprocess.run(
            ["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", array_str],
            check=True,
        )

        fast_cmd = f"{python_bin} {spic_entrypoint} trigger"
        smart_cmd = f"{python_bin} {spic_entrypoint} trigger --smart"

        # Configure Fast Shortcut (Ctrl+Alt+Space)
        schema_fast = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-fast/"
        subprocess.run(["gsettings", "set", schema_fast, "name", "Spic Fast Voice Typing"], check=True)
        subprocess.run(["gsettings", "set", schema_fast, "command", fast_cmd], check=True)
        subprocess.run(["gsettings", "set", schema_fast, "binding", "<Control><Alt>space"], check=True)

        # Configure Smart Shortcut (Ctrl+Super+Space)
        schema_smart = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-smart/"
        subprocess.run(["gsettings", "set", schema_smart, "name", "Spic Smart Voice Copilot"], check=True)
        subprocess.run(["gsettings", "set", schema_smart, "command", smart_cmd], check=True)
        subprocess.run(["gsettings", "set", schema_smart, "binding", "<Control><Super>space"], check=True)

        print("[Spic] Successfully configured GNOME Shortcuts:")
        print("  - Fast Voice Typing:  <Ctrl> + <Alt> + <Space>")
        print("  - Smart Voice Copilot: <Ctrl> + <Super> + <Space>")
        return True

    except Exception as e:
        print(f"[Spic] Failed to register GNOME shortcuts: {e}")
        return False

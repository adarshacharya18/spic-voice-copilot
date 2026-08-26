"""GNOME Global Shortcut Management, Conflict Detection, and Free Key Guidance."""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger("spic.shortcuts")

# Curated catalog of ergonomic candidate hotkeys for voice dictation
RECOMMENDED_CANDIDATES = [
    ("<Control><Alt>space", "Ctrl + Alt + Space", "Classic thumb-reach dictation trigger (Recommended for Fast)"),
    ("<Control><Super>space", "Ctrl + Super + Space", "Thumb-reach intelligence trigger (Recommended for Smart)"),
    ("<Control><Alt>m", "Ctrl + Alt + M", "M for Microphone / Speech trigger"),
    ("<Control><Alt>v", "Ctrl + Alt + V", "V for Voice / Verbal typing"),
    ("<Control><Shift>space", "Ctrl + Shift + Space", "High-ergonomic spacebar combination"),
    ("<Control><Super>k", "Ctrl + Super + K", "K for Knowledge / Voice Copilot"),
    ("<Control><Alt>d", "Ctrl + Alt + D", "D for Dictation"),
    ("<Control><Alt>i", "Ctrl + Alt + I", "I for Intelligence"),
    ("<Control><Alt>Return", "Ctrl + Alt + Enter", "Enter key speech trigger"),
    ("<Control><Super>d", "Ctrl + Super + D", "D for Direct Dictation"),
]


def normalize_binding(b: str) -> str:
    """Normalize shortcut strings (e.g. 'ctrl+alt+m', '<Primary><Alt>m') into canonical GNOME format."""
    b = b.strip()
    tokens = re.findall(r"<[A-Za-z]+>|[A-Za-z0-9_]+", b)
    mods = []
    key = ""

    for t in tokens:
        clean = t.strip("<>").lower()
        if clean in ("ctrl", "control", "primary"):
            mods.append("<Control>")
        elif clean in ("alt", "meta"):
            mods.append("<Alt>")
        elif clean in ("super", "win", "windows", "mod4"):
            mods.append("<Super>")
        elif clean in ("shift",):
            mods.append("<Shift>")
        else:
            key = t.strip("<>")

    # Stable canonical modifier order
    ordered_mods = []
    for m in ["<Control>", "<Alt>", "<Super>", "<Shift>"]:
        if m in mods:
            ordered_mods.append(m)

    if not key:
        return b

    # Capitalize standard keys (e.g., Return, Tab, Escape, F1-F12) or lowercase letters
    if key.lower() in ("space", "tab", "return", "escape"):
        key_formatted = key.lower()
    elif key.upper().startswith("F") and key[1:].isdigit():
        key_formatted = key.upper()
    else:
        key_formatted = key.lower()

    return "".join(ordered_mods) + key_formatted


def format_binding_label(binding: str) -> str:
    """Convert canonical binding (e.g. '<Control><Alt>space') into human-friendly 'Ctrl + Alt + Space'."""
    norm = normalize_binding(binding)
    parts = []
    if "<Control>" in norm:
        parts.append("Ctrl")
    if "<Alt>" in norm:
        parts.append("Alt")
    if "<Super>" in norm:
        parts.append("Super")
    if "<Shift>" in norm:
        parts.append("Shift")

    key = re.sub(r"<[A-Za-z]+>", "", norm)
    if key:
        parts.append(key.capitalize())

    return " + ".join(parts)


def get_active_system_bindings() -> dict[str, dict]:
    """Scan all active GNOME keybindings across window manager, shell, and media-keys."""
    schemas = [
        "org.gnome.desktop.wm.keybindings",
        "org.gnome.shell.keybindings",
        "org.gnome.settings-daemon.plugins.media-keys",
    ]
    bindings_map: dict[str, dict] = {}

    for schema in schemas:
        try:
            res = subprocess.run(["gsettings", "list-keys", schema], capture_output=True, text=True)
            if res.returncode != 0:
                continue

            for k in res.stdout.splitlines():
                k = k.strip()
                if not k:
                    continue

                val_res = subprocess.run(["gsettings", "get", schema, k], capture_output=True, text=True)
                val = val_res.stdout.strip()

                found_bindings = re.findall(r"'([^']+)'", val)
                for b in found_bindings:
                    if b and b != "disabled":
                        norm = normalize_binding(b).lower()
                        bindings_map[norm] = {
                            "raw_binding": b,
                            "normalized": norm,
                            "schema": schema,
                            "key": k,
                            "action_name": k.replace("-", " ").title(),
                            "type": "system",
                        }
        except Exception:
            pass

    # Also scan custom user shortcuts
    try:
        cmd_get = ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"]
        result = subprocess.run(cmd_get, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            raw_paths = re.findall(r"'([^']+)'", result.stdout)
            for path in raw_paths:
                # Ignore Spic's own paths when detecting external conflicts
                if "spic-fast" in path or "spic-smart" in path:
                    continue
                schema_path = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}"
                b_res = subprocess.run(["gsettings", "get", schema_path, "binding"], capture_output=True, text=True)
                name_res = subprocess.run(["gsettings", "get", schema_path, "name"], capture_output=True, text=True)
                raw_b = b_res.stdout.strip().strip("'")
                name = name_res.stdout.strip().strip("'")
                if raw_b and raw_b != "disabled":
                    norm = normalize_binding(raw_b).lower()
                    bindings_map[norm] = {
                        "raw_binding": raw_b,
                        "normalized": norm,
                        "schema": schema_path,
                        "key": "custom-keybinding",
                        "action_name": name or "Custom User Shortcut",
                        "type": "custom",
                    }
    except Exception:
        pass

    return bindings_map


def check_shortcut_conflict(binding: str) -> Optional[dict]:
    """Check if a proposed shortcut conflicts with an existing GNOME shortcut."""
    norm = normalize_binding(binding).lower()
    system_bindings = get_active_system_bindings()
    return system_bindings.get(norm)


def get_free_recommended_shortcuts() -> list[tuple[str, str, str]]:
    """Return a list of ergonomic candidate shortcuts that are 100% free / unassigned."""
    active_bindings = get_active_system_bindings()
    free_list = []

    for binding, label, desc in RECOMMENDED_CANDIDATES:
        norm = normalize_binding(binding).lower()
        if norm not in active_bindings:
            free_list.append((binding, label, desc))

    return free_list


def register_gnome_shortcuts(
    python_bin: str,
    spic_entrypoint: str,
    fast_binding: str = "<Control><Alt>space",
    smart_binding: str = "<Control><Super>space",
) -> bool:
    """Register custom GNOME shortcuts for Spic Fast and Smart triggers in gsettings."""
    try:
        res = subprocess.run(["which", "gsettings"], capture_output=True, text=True)
        if res.returncode != 0:
            print("[Spic] gsettings not found. Manual shortcut configuration required.")
            return False

        fast_norm = normalize_binding(fast_binding)
        smart_norm = normalize_binding(smart_binding)

        cmd_get = ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"]
        result = subprocess.run(cmd_get, capture_output=True, text=True, check=True)
        current_val = result.stdout.strip()

        paths = []
        if current_val.startswith("[") and current_val.endswith("]"):
            raw_paths = re.findall(r"'([^']+)'", current_val)
            paths = [p for p in raw_paths if p.strip()]

        fast_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-fast/"
        smart_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spic-smart/"

        if fast_path not in paths:
            paths.append(fast_path)
        if smart_path not in paths:
            paths.append(smart_path)

        array_str = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
        subprocess.run(
            ["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", array_str],
            check=True,
        )

        fast_cmd = f"{python_bin} {spic_entrypoint} trigger"
        smart_cmd = f"{python_bin} {spic_entrypoint} trigger --smart"

        # Configure Fast Shortcut
        schema_fast = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{fast_path}"
        subprocess.run(["gsettings", "set", schema_fast, "name", "Spic Fast Voice Typing"], check=True)
        subprocess.run(["gsettings", "set", schema_fast, "command", fast_cmd], check=True)
        subprocess.run(["gsettings", "set", schema_fast, "binding", fast_norm], check=True)

        # Configure Smart Shortcut
        schema_smart = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{smart_path}"
        subprocess.run(["gsettings", "set", schema_smart, "name", "Spic Smart Voice Copilot"], check=True)
        subprocess.run(["gsettings", "set", schema_smart, "command", smart_cmd], check=True)
        subprocess.run(["gsettings", "set", schema_smart, "binding", smart_norm], check=True)

        logger.info(f"GNOME Shortcuts registered: Fast={fast_norm}, Smart={smart_norm}")
        return True

    except Exception as e:
        logger.error(f"Failed to register GNOME shortcuts: {e}")
        return False

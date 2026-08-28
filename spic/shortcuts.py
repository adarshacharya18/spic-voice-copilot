"""GNOME Global Shortcut Management, Conflict Detection, and Free Key Guidance."""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from typing import Callable, Optional

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


def _normalize_pynput_key(k: object) -> Optional[object]:
    """Map left/right variants and ASCII control characters to canonical key identifiers for pynput."""
    if k is None:
        return None

    try:
        from pynput.keyboard import Key, KeyCode
        if isinstance(k, Key):
            if k in (Key.alt_r, Key.alt_gr):
                return Key.alt_r
            if k == Key.ctrl_r:
                return Key.ctrl_r
            if k in (Key.ctrl, Key.ctrl_l):
                return Key.ctrl
            if k in (Key.alt, Key.alt_l):
                return Key.alt
            if k in (Key.shift, Key.shift_l, Key.shift_r):
                return Key.shift
            if k in (Key.cmd, Key.cmd_l, Key.cmd_r):
                return Key.cmd
            return k

        if isinstance(k, KeyCode):
            if k.char:
                val = ord(k.char)
                # In Linux X11/XWayland, Ctrl+Letter produces ASCII control codes (1-26)
                if 1 <= val <= 26:
                    return chr(val + 96)
                return k.char.lower()
            if k.vk:
                return f"vk_{k.vk}"
    except Exception:
        pass

    return None


def parse_hotkey_combination(binding: str) -> set[object]:
    """Parse a shortcut binding string (e.g. '<RightAlt>', '<Control>m', '<CapsLock>', '<F8>') into a set of canonical keys."""
    try:
        from pynput.keyboard import Key
    except ImportError:
        return set()

    target_keys: set[object] = set()
    b = binding.lower()

    if "rightalt" in b or "alt_r" in b or "altgr" in b or "right_alt" in b:
        target_keys.add(Key.alt_r)
    elif "alt" in b or "meta" in b:
        target_keys.add(Key.alt)

    if "rightctrl" in b or "ctrl_r" in b or "right_ctrl" in b or "rightcontrol" in b:
        target_keys.add(Key.ctrl_r)
    elif "ctrl" in b or "control" in b or "primary" in b:
        target_keys.add(Key.ctrl)

    if "rightshift" in b or "shift_r" in b or "right_shift" in b:
        target_keys.add(Key.shift_r)
    elif "shift" in b:
        target_keys.add(Key.shift)

    if "super" in b or "win" in b or "mod4" in b or "cmd" in b:
        target_keys.add(Key.cmd)
    if "caps" in b or "capslock" in b or "caps_lock" in b:
        target_keys.add(Key.caps_lock)
    if "scroll" in b or "scrolllock" in b:
        target_keys.add(Key.scroll_lock)
    if "pause" in b:
        target_keys.add(Key.pause)

    # Check function keys (f1 - f12)
    for fn in range(1, 13):
        if f"<f{fn}>" in b or f"f{fn}" == b.strip("<> "):
            if hasattr(Key, f"f{fn}"):
                target_keys.add(getattr(Key, f"f{fn}"))

    main_key = re.sub(r"<[a-z0-9_]+>", "", b).strip("+-_ ")
    if main_key:
        if main_key == "space":
            target_keys.add(Key.space)
        elif main_key in ("return", "enter"):
            target_keys.add(Key.enter)
        elif main_key == "tab":
            target_keys.add(Key.tab)
        elif main_key == "escape":
            target_keys.add(Key.esc)
        elif len(main_key) == 1:
            target_keys.add(main_key.lower())

    return target_keys


def _get_target_ecodes_groups(binding: str) -> list[set[int]]:
    """Parse shortcut binding into groups of Linux evdev scancodes."""
    try:
        from evdev import ecodes
    except ImportError:
        return []

    b = binding.lower()
    groups: list[set[int]] = []

    if "rightalt" in b or "alt_r" in b or "altgr" in b or "right_alt" in b:
        groups.append({ecodes.KEY_RIGHTALT})
    elif "leftalt" in b or "alt_l" in b or "left_alt" in b:
        groups.append({ecodes.KEY_LEFTALT})
    elif "alt" in b or "meta" in b:
        groups.append({ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT})

    if "rightctrl" in b or "ctrl_r" in b or "right_ctrl" in b or "rightcontrol" in b:
        groups.append({ecodes.KEY_RIGHTCTRL})
    elif "leftctrl" in b or "ctrl_l" in b or "left_ctrl" in b or "leftcontrol" in b:
        groups.append({ecodes.KEY_LEFTCTRL})
    elif "ctrl" in b or "control" in b or "primary" in b:
        groups.append({ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL})

    if "rightshift" in b or "shift_r" in b or "right_shift" in b:
        groups.append({ecodes.KEY_RIGHTSHIFT})
    elif "leftshift" in b or "shift_l" in b or "left_shift" in b:
        groups.append({ecodes.KEY_LEFTSHIFT})
    elif "shift" in b:
        groups.append({ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT})

    if "super" in b or "win" in b or "cmd" in b:
        groups.append({ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA})
    if "caps" in b or "capslock" in b or "caps_lock" in b:
        groups.append({ecodes.KEY_CAPSLOCK})
    if "scroll" in b or "scrolllock" in b:
        groups.append({ecodes.KEY_SCROLLLOCK})
    if "pause" in b:
        groups.append({ecodes.KEY_PAUSE})

    # Check function keys (f1 - f12)
    for fn in range(1, 13):
        if f"<f{fn}>" in b or f"f{fn}" == b.strip("<> "):
            code_name = f"KEY_F{fn}"
            if hasattr(ecodes, code_name):
                groups.append({getattr(ecodes, code_name)})

    main_key = re.sub(r"<[a-z0-9_]+>", "", b).strip("+-_ ")
    if main_key:
        if main_key == "space":
            groups.append({ecodes.KEY_SPACE})
        elif main_key in ("return", "enter"):
            groups.append({ecodes.KEY_ENTER})
        elif main_key == "tab":
            groups.append({ecodes.KEY_TAB})
        elif main_key == "escape":
            groups.append({ecodes.KEY_ESC})
        elif len(main_key) == 1:
            code_name = f"KEY_{main_key.upper()}"
            if hasattr(ecodes, code_name):
                groups.append({getattr(ecodes, code_name)})

    return groups


class GlobalKeyHoldListener:
    """Dual-layer global key-hold listener utilizing native Linux evdev with pynput fallback."""

    def __init__(
        self,
        binding: str = "<RightControl>",
        on_hold_start: Optional[Callable[[], None]] = None,
        on_hold_stop: Optional[Callable[[], None]] = None,
        hold_delay_ms: int = 500,
    ):
        self.binding = binding
        self.on_hold_start = on_hold_start
        self.on_hold_stop = on_hold_stop
        self.hold_delay_seconds = max(0.0, hold_delay_ms / 1000.0)

        self._pynput_target_keys = parse_hotkey_combination(binding)
        self._evdev_target_groups = _get_target_ecodes_groups(binding)

        self._current_pressed_pynput: set[object] = set()
        self._current_pressed_ecodes: set[int] = set()

        self._is_holding = False
        self._evdev_active = False
        self._pynput_listener = None
        self._evdev_thread = None
        self._pending_timer: Optional[threading.Timer] = None
        self._running = False
        self._lock = threading.RLock()
        self._last_state_change_time = 0.0

    @property
    def is_holding(self) -> bool:
        return self._is_holding

    def start(self) -> None:
        """Start hardware evdev listener and pynput fallback listener in background."""
        if self._running:
            return

        self._running = True

        # 1. Start evdev hardware kernel listener
        self._start_evdev_listener()

        # 2. Start pynput fallback listener
        self._start_pynput_listener()

        logger.info(f"Global key-hold listener active for '{self.binding}' (hold delay: {int(self.hold_delay_seconds*1000)}ms)")

    def stop(self) -> None:
        """Stop all listeners."""
        self._running = False
        self._evdev_active = False
        with self._lock:
            if self._pending_timer is not None:
                try:
                    self._pending_timer.cancel()
                except Exception:
                    pass
                self._pending_timer = None

        if self._pynput_listener is not None:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None

    def _on_key_match_start(self) -> None:
        """Called when key combination is pressed. Starts the hold delay timer."""
        with self._lock:
            if self._is_holding or self._pending_timer is not None:
                return

            if self.hold_delay_seconds <= 0.0:
                self._trigger_hold_start()
                return

            self._pending_timer = threading.Timer(self.hold_delay_seconds, self._on_timer_fired)
            self._pending_timer.daemon = True
            self._pending_timer.start()

    def _on_key_match_stop(self) -> None:
        """Called when key combination is released. Cancels pending timer or stops active hold."""
        with self._lock:
            if self._pending_timer is not None:
                try:
                    self._pending_timer.cancel()
                except Exception:
                    pass
                self._pending_timer = None

            if self._is_holding:
                self._trigger_hold_stop()

    def _on_timer_fired(self) -> None:
        """Timer callback when key was held past hold_delay_seconds threshold."""
        with self._lock:
            self._pending_timer = None
        self._trigger_hold_start()

    def _trigger_hold_start(self) -> None:
        """Trigger hold start safely without blocking key listener thread."""
        with self._lock:
            now = time.time()
            if not self._is_holding:
                self._is_holding = True
                self._last_state_change_time = now
                should_call = True
            else:
                should_call = False

        if should_call:
            logger.info(f"🎯 Hold confirmed for '{self.binding}' (>{int(self.hold_delay_seconds*1000)}ms). Starting stream...")
            if self.on_hold_start:
                try:
                    threading.Thread(target=self.on_hold_start, daemon=True).start()
                except Exception as e:
                    logger.error(f"Error in on_hold_start: {e}")

    def _trigger_hold_stop(self) -> None:
        """Trigger hold stop safely without blocking key listener thread."""
        with self._lock:
            now = time.time()
            if self._is_holding:
                self._is_holding = False
                self._last_state_change_time = now
                should_call = True
            else:
                should_call = False

        if should_call:
            logger.info(f"🛑 Release detected for '{self.binding}'. Stopping stream...")
            if self.on_hold_stop:
                try:
                    threading.Thread(target=self.on_hold_stop, daemon=True).start()
                except Exception as e:
                    logger.error(f"Error in on_hold_stop: {e}")

    # =========================================================================
    # 1. Native Evdev Kernel Hardware Listener
    # =========================================================================
    def _start_evdev_listener(self) -> None:
        if not self._evdev_target_groups:
            return

        def _scan_keyboards():
            try:
                import evdev
                from evdev import ecodes
            except ImportError:
                return []

            keyboards = []
            try:
                for path in evdev.list_devices():
                    try:
                        d = evdev.InputDevice(path)
                        caps = d.capabilities()
                        if ecodes.EV_KEY in caps:
                            klist = caps[ecodes.EV_KEY]
                            if ecodes.KEY_A in klist and ecodes.KEY_SPACE in klist and "spic virtual" not in d.name.lower():
                                keyboards.append(d)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Evdev enumeration notice: {e}")
            return keyboards

        def _evdev_loop():
            import select
            try:
                from evdev import ecodes
            except ImportError:
                return

            keyboards = _scan_keyboards()
            last_scan_time = time.time()

            if keyboards:
                self._evdev_active = True
                logger.info(f"Evdev listening on {len(keyboards)} hardware keyboard device(s)")

            while self._running:
                try:
                    now = time.time()
                    # Periodically refresh keyboard devices every 4 seconds or when list is empty
                    if not keyboards or (now - last_scan_time > 4.0):
                        active_paths = {d.path for d in keyboards}
                        new_devs = _scan_keyboards()
                        for nd in new_devs:
                            if nd.path not in active_paths:
                                keyboards.append(nd)
                        last_scan_time = now
                        if keyboards:
                            self._evdev_active = True

                    if not keyboards:
                        self._evdev_active = False
                        time.sleep(0.5)
                        continue

                    r, _, _ = select.select(keyboards, [], [], 0.5)
                    dead_devices = []

                    for dev in r:
                        try:
                            for event in dev.read():
                                if event.type == ecodes.EV_KEY:
                                    code = event.code
                                    val = event.value  # 0: release, 1: press, 2: hold/repeat

                                    with self._lock:
                                        if val in (1, 2):
                                            self._current_pressed_ecodes.add(code)
                                        elif val == 0:
                                            self._current_pressed_ecodes.discard(code)

                                        # Check if all target groups have at least one active key
                                        is_match = all(
                                            any(k in self._current_pressed_ecodes for k in grp)
                                            for grp in self._evdev_target_groups
                                        )

                                    if is_match:
                                        self._on_key_match_start()
                                    else:
                                        self._on_key_match_stop()
                        except (OSError, IOError) as err:
                            logger.debug(f"Evdev device disconnected ({dev.path}): {err}")
                            dead_devices.append(dev)

                    if dead_devices:
                        for d in dead_devices:
                            try:
                                d.close()
                            except Exception:
                                pass
                            if d in keyboards:
                                keyboards.remove(d)

                except Exception as e:
                    if self._running:
                        time.sleep(0.5)

        self._evdev_thread = threading.Thread(target=_evdev_loop, daemon=True)
        self._evdev_thread.start()

    # =========================================================================
    # 2. Pynput Fallback Listener
    # =========================================================================
    def _start_pynput_listener(self) -> None:
        try:
            import pynput
            self._pynput_listener = pynput.keyboard.Listener(
                on_press=self._on_pynput_press,
                on_release=self._on_pynput_release,
            )
            self._pynput_listener.daemon = True
            self._pynput_listener.start()
        except Exception as e:
            logger.debug(f"Pynput listener notice: {e}")

    def _on_pynput_press(self, key) -> None:
        if self._evdev_active:
            return

        norm = _normalize_pynput_key(key)
        if norm is None:
            return

        with self._lock:
            self._current_pressed_pynput.add(norm)
            is_match = self._pynput_target_keys and self._pynput_target_keys.issubset(self._current_pressed_pynput)

        if is_match:
            self._on_key_match_start()

    def _on_pynput_release(self, key) -> None:
        if self._evdev_active:
            return

        norm = _normalize_pynput_key(key)
        if norm is None:
            return

        with self._lock:
            self._current_pressed_pynput.discard(norm)
            is_match = self._pynput_target_keys and self._pynput_target_keys.issubset(self._current_pressed_pynput)

        if not is_match:
            self._on_key_match_stop()

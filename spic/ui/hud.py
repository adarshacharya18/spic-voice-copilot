"""Native Linux GTK3/Cairo True-Transparent HUD with 60 FPS morphing string physics."""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from typing import Literal, Optional

# Ensure access to system python-gi on Ubuntu / Linux
if "/usr/lib/python3/dist-packages" not in sys.path:
    sys.path.append("/usr/lib/python3/dist-packages")

# Force X11/XWayland backend for GTK so GNOME Mutter honors exact top-middle screen positioning
os.environ.setdefault("GDK_BACKEND", "x11,wayland,*")

from spic.config import UIConfig

HAS_GTK = False
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib
    import cairo
    HAS_GTK = True
except Exception:
    HAS_GTK = False


def _ease_out_back(t: float) -> float:
    """Spring overshoot easing curve."""
    c1 = 1.35
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def _ease_in_cubic(t: float) -> float:
    """Smooth exit easing curve."""
    return t * t * t


class FloatingHUD:
    """Ultra-smooth floating HUD with 100% true-transparent alpha compositing."""

    def __init__(self, config: UIConfig):
        self.config = config
        self._state: Literal["listening", "processing", "done"] = "listening"
        self._visibility: Literal["hidden", "entering", "visible", "exiting"] = "hidden"
        self._anim_progress = 0.0
        self._morph_progress = 0.0  # 0.0 (Bars) -> 0.5 (Flat String) -> 1.0 (String Waves)
        self._done_decay = 1.0      # 1.0 (Waving) -> 0.0 (Stopped Flat String)
        self._audio_level = 0.15
        self._target_audio_level = 0.15
        self._phase = 0.0

        self._win_w = max(180, self.config.hud_width or 190)
        self._win_h = max(42, self.config.hud_height or 46)

        self._gtk_window: Optional[Gtk.Window] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the HUD window in a background thread."""
        if not self.config.show_hud or self._thread is not None:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_gtk_gui, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Close HUD window."""
        self._running = False
        if HAS_GTK and self._gtk_window:
            try:
                GLib.idle_add(Gtk.main_quit)
            except Exception:
                pass

    def show_listening(self) -> None:
        """Show dynamic audio-reactive vertical bars."""
        with self._lock:
            self._state = "listening"
            self._morph_progress = 0.0
            self._done_decay = 1.0
            self._audio_level = 0.25
            self._target_audio_level = 0.25
            self._visibility = "entering"
            if self._anim_progress <= 0.05:
                self._anim_progress = 0.0
        self._trigger_update()

    def show_processing(self) -> None:
        """Settle bars into middle to form a single string, then that string waves."""
        with self._lock:
            self._state = "processing"
            self._morph_progress = 0.0
            if self._visibility == "hidden":
                self._visibility = "entering"
        self._trigger_update()

    def show_done(self, message: str = "✓ Injected") -> None:
        """Damp wave oscillations until string stops flat, then exit."""
        with self._lock:
            self._state = "done"
            self._done_decay = 1.0
        self._trigger_update()

        def _delayed_exit():
            time.sleep(0.8)
            self.hide()

        threading.Thread(target=_delayed_exit, daemon=True).start()

    def hide(self) -> None:
        """Initiate graceful exit transition."""
        with self._lock:
            if self._visibility != "hidden":
                self._visibility = "exiting"
        self._trigger_update()

    def update_audio_level(self, level: float) -> None:
        """Update live audio level (RMS)."""
        with self._lock:
            target = max(0.15, min(1.0, level * 10.0))
            self._target_audio_level = target

    def _trigger_update(self) -> None:
        if HAS_GTK and self._gtk_window:
            try:
                GLib.idle_add(self._gtk_window.queue_draw)
            except Exception:
                pass

    def _get_target_coords(self) -> tuple[int, int]:
        """Calculate exact top-middle screen coordinates."""
        try:
            screen = Gdk.Screen.get_default()
            if screen:
                screen_w = screen.get_width()
                screen_h = screen.get_height()
            else:
                screen_w, screen_h = 1920, 1080

            pos_x = max(0, (screen_w - self._win_w) // 2)

            pos_mode = getattr(self.config, "hud_position", "top_center")
            if pos_mode == "middle_center":
                pos_y = max(0, (screen_h - self._win_h) // 2)
            elif pos_mode == "bottom_center":
                pos_y = max(0, screen_h - self._win_h - 20)
            else:
                # Placed cleanly below Ubuntu top header bar and date/clock (~32px bar + ~22px breathing room)
                pos_y = 54

            return (pos_x, pos_y)
        except Exception:
            return (0, 54)

    def _run_gtk_gui(self) -> None:
        """Native GTK3 + Cairo GUI loop with 100% RGBA transparent compositing."""
        if not HAS_GTK:
            return

        # On Wayland compositors (GNOME Mutter), native Wayland strips custom coordinates.
        # Using XWayland with POPUP override-redirect bypasses GNOME's center-new-windows setting.
        try:
            Gdk.set_allowed_backends("x11,wayland,*")
        except Exception:
            pass

        Gtk.init(None)

        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_title("Spic Wave")
        win.set_app_paintable(True)
        win.set_keep_above(True)
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)

        # Enable true 32-bit RGBA hardware visual for alpha transparency
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            win.set_visual(visual)

        win.set_default_size(self._win_w, self._win_h)
        pos_x, pos_y = self._get_target_coords()
        win.move(pos_x, pos_y)

        win.connect("draw", self._on_cairo_draw)
        self._gtk_window = win

        # 60 FPS animation timer (16ms)
        GLib.timeout_add(16, self._on_gtk_tick)

        Gtk.main()

    def _on_gtk_tick(self) -> bool:
        """60 FPS physics and frame tick."""
        if not self._running:
            return False

        with self._lock:
            # 1. Entrance / Exit visibility
            if self._visibility == "entering":
                self._anim_progress += 0.08
                if self._anim_progress >= 1.0:
                    self._anim_progress = 1.0
                    self._visibility = "visible"

            elif self._visibility == "exiting":
                self._anim_progress -= 0.075
                if self._anim_progress <= 0.0:
                    self._anim_progress = 0.0
                    self._visibility = "hidden"

            # 2. Smooth Bar -> Single String -> Wave Morphing
            if self._state == "processing":
                if self._morph_progress < 1.0:
                    self._morph_progress = min(1.0, self._morph_progress + 0.04)

            # 3. Wave -> Flat String Settling Decay
            if self._state == "done":
                if self._done_decay > 0.0:
                    self._done_decay = max(0.0, self._done_decay - 0.033)

            self._audio_level += (self._target_audio_level - self._audio_level) * 0.22
            self._target_audio_level *= 0.96
            self._phase += 0.12

        if self._gtk_window:
            if self._visibility == "hidden":
                self._gtk_window.hide()
            else:
                pos_x, pos_y = self._get_target_coords()
                self._gtk_window.move(pos_x, pos_y)
                self._gtk_window.show_all()
                self._gtk_window.queue_draw()

        return True

    def _on_cairo_draw(self, widget: Gtk.Widget, cr: cairo.Context) -> bool:
        """Vector render using Cairo with true alpha=0.0 transparent corners."""
        with self._lock:
            vis = self._visibility
            progress = self._anim_progress
            state = self._state
            level = self._audio_level
            phase = self._phase
            morph = self._morph_progress
            done_decay = self._done_decay

        if vis == "hidden":
            return False

        w = float(widget.get_allocated_width())
        h = float(widget.get_allocated_height())
        cy = h / 2.0
        r = (h / 2.0) - 2.0

        # Dynamic Alpha
        if vis == "entering":
            alpha = min(0.96, progress * 1.1)
        elif vis == "exiting":
            alpha = max(0.0, progress * 0.96)
        else:
            alpha = 0.96

        # =========================================================================
        # 1. Clear Entire Surface to 100% TRUE TRANSPARENT (Alpha = 0.0)
        # =========================================================================
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # =========================================================================
        # 2. Draw Rounded Glass Pill Capsule
        # =========================================================================
        x1, y1 = 2.0, 2.0
        x2, y2 = w - 2.0, h - 2.0

        cr.new_path()
        cr.arc(x1 + r, y1 + r, r, math.pi / 2.0, 3.0 * math.pi / 2.0)
        cr.line_to(x2 - r, y1)
        cr.arc(x2 - r, y1 + r, r, -math.pi / 2.0, math.pi / 2.0)
        cr.line_to(x1 + r, y2)
        cr.close_path()

        # Dark Cosmic Glass Surface Fill
        cr.set_source_rgba(0.06, 0.07, 0.10, 0.95 * alpha)
        cr.fill_preserve()

        # Outer Soft Ambient Glow Stroke
        cr.set_source_rgba(0.05, 0.22, 0.30, 0.80 * alpha)
        cr.set_line_width(3.0)
        cr.stroke_preserve()

        # Sharp Glowing Cyan Glass Border
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.90 * alpha)
        cr.set_line_width(1.6)
        cr.stroke()

        # Physical Anchors (seamless 0px gap to left & right inner border apexes)
        x_left_anchor = x1
        x_right_anchor = x2
        total_span = x_right_anchor - x_left_anchor

        def _edge_envelope(nx: float) -> float:
            return math.sin(nx * math.pi) ** 0.85

        # =========================================================================
        # STATE 1: LISTENING (Pure Vertical Audio-Reactive Spectrum Bars Only)
        # =========================================================================
        if state == "listening":
            num_bars = 28
            bar_pad_x = x_left_anchor + 6.0
            bar_area_w = total_span - 12.0
            bar_spacing = bar_area_w / float(num_bars)
            max_bar_h = (h * 0.72) * min(1.0, progress * 1.2)
            min_bar_h = 4.0

            cr.set_source_rgba(0.0, 0.95, 1.0, 0.95 * alpha)
            cr.set_line_width(3.0)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)

            for i in range(num_bars):
                nx = i / float(num_bars - 1)
                bx = bar_pad_x + (i + 0.5) * bar_spacing

                freq_osc = (
                    math.sin(i * 1.05 - phase * 3.8) * 0.40 +
                    math.cos(i * 1.75 + phase * 2.6) * 0.35 +
                    math.sin(nx * 12.0 - phase * 4.6) * 0.25
                )
                harmonic = 0.50 + 0.50 * freq_osc

                dyn_h = min_bar_h + (max_bar_h - min_bar_h) * (level * 0.85 + 0.15) * harmonic
                dyn_h = max(min_bar_h, min(max_bar_h, dyn_h))

                cr.move_to(bx, cy - (dyn_h / 2.0))
                cr.line_to(bx, cy + (dyn_h / 2.0))
                cr.stroke()

        # =========================================================================
        # STATE 2: PROCESSING (Bars Settle into Middle -> Fully Anchored String Waves)
        # =========================================================================
        elif state == "processing":
            if morph <= 0.5:
                collapse_k = 1.0 - (morph / 0.5)

                # 1. Full-span baseline string
                cr.set_source_rgba(0.0, 0.95, 1.0, 0.95 * alpha)
                cr.set_line_width(2.2)
                cr.move_to(x_left_anchor, cy)
                cr.line_to(x_right_anchor, cy)
                cr.stroke()

                # 2. Compressing bars
                if collapse_k > 0.05:
                    num_bars = 28
                    bar_pad_x = x_left_anchor + 6.0
                    bar_area_w = total_span - 12.0
                    bar_spacing = bar_area_w / float(num_bars)

                    cr.set_source_rgba(0.22, 0.74, 0.97, 0.85 * alpha)
                    cr.set_line_width(2.8 * collapse_k)
                    cr.set_line_cap(cairo.LINE_CAP_ROUND)

                    for i in range(num_bars):
                        bx = bar_pad_x + (i + 0.5) * bar_spacing
                        freq_osc = math.sin(i * 1.05 - phase * 3.8) * 0.5 + math.cos(i * 1.75 + phase * 2.6) * 0.5
                        harmonic = 0.50 + 0.50 * freq_osc

                        bar_h = max(2.0, (h * 0.65) * collapse_k * harmonic)
                        cr.move_to(bx, cy - (bar_h / 2.0))
                        cr.line_to(bx, cy + (bar_h / 2.0))
                        cr.stroke()

            # Phase B: The fully anchored string waves from border to border
            else:
                wave_growth = (morph - 0.5) / 0.5
                think_amp = (h * 0.28) * wave_growth * min(1.0, progress * 1.2)
                step = 2.0

                # Ambient glow wave
                if wave_growth > 0.3:
                    cr.set_source_rgba(0.22, 0.74, 0.97, 0.60 * alpha)
                    cr.set_line_width(1.6)
                    cr.move_to(x_left_anchor, cy)
                    for px in range(0, int(total_span) + 1, int(step)):
                        x = x_left_anchor + px
                        nx = px / total_span
                        env = _edge_envelope(nx)
                        y_glow = cy + math.sin(nx * 12.0 + phase * 2.8) * (think_amp * 0.65 * env)
                        cr.line_to(x, y_glow)
                    cr.line_to(x_right_anchor, cy)
                    cr.stroke()

                # Core primary wave string
                cr.set_source_rgba(0.0, 0.95, 1.0, 0.95 * alpha)
                cr.set_line_width(2.4)
                cr.move_to(x_left_anchor, cy)
                for px in range(0, int(total_span) + 1, int(step)):
                    x = x_left_anchor + px
                    nx = px / total_span
                    env = _edge_envelope(nx)
                    y_wave = cy + math.sin(nx * 8.0 - phase * 3.6) * (think_amp * env)
                    cr.line_to(x, y_wave)
                cr.line_to(x_right_anchor, cy)
                cr.stroke()

        # =========================================================================
        # STATE 3: DONE (String Wave Oscillations Damp Down Until Flat & Still)
        # =========================================================================
        elif state == "done":
            step = 2.0
            done_amp = (h * 0.28) * done_decay * min(1.0, progress)

            if done_decay > 0.06:
                # Ambient glow wave
                if done_decay > 0.3:
                    cr.set_source_rgba(0.22, 0.74, 0.97, 0.60 * alpha)
                    cr.set_line_width(1.6)
                    cr.move_to(x_left_anchor, cy)
                    for px in range(0, int(total_span) + 1, int(step)):
                        x = x_left_anchor + px
                        nx = px / total_span
                        env = _edge_envelope(nx)
                        y_glow = cy + math.sin(nx * 12.0 + phase * 2.4) * (done_amp * 0.6 * env)
                        cr.line_to(x, y_glow)
                    cr.line_to(x_right_anchor, cy)
                    cr.stroke()

                # Primary wave string
                cr.set_source_rgba(0.0, 0.95, 1.0, 0.95 * alpha)
                cr.set_line_width(2.4)
                cr.move_to(x_left_anchor, cy)
                for px in range(0, int(total_span) + 1, int(step)):
                    x = x_left_anchor + px
                    nx = px / total_span
                    env = _edge_envelope(nx)
                    y_wave = cy + math.sin(nx * 8.0 - phase * 3.0) * (done_amp * env)
                    cr.line_to(x, y_wave)
                cr.line_to(x_right_anchor, cy)
                cr.stroke()

            # Flat stopped resting string
            else:
                cr.set_source_rgba(0.0, 0.95, 1.0, 0.95 * alpha)
                cr.set_line_width(2.4)
                cr.move_to(x_left_anchor, cy)
                cr.line_to(x_right_anchor, cy)
                cr.stroke()

        return False

"""High-fidelity floating HUD: Fully anchored string with seamless window integration."""

from __future__ import annotations

import math
import threading
import time
from typing import Literal, Optional
import tkinter as tk

from spic.config import UIConfig

HUD_SURFACE_BG = "#0F1018"
THEME_CYAN_CORE = "#00F2FE"       # Primary electric cyan
THEME_CYAN_GLOW = "#38BDF8"       # Secondary ambient glow
CAPSULE_BORDER_COLOR = "#22D3EE"    # Sharp glowing pill perimeter
CAPSULE_GLOW_OUTLINE = "#0E3A4D"    # Outer soft ambient stroke


def _ease_out_back(t: float) -> float:
    """Spring overshoot easing curve."""
    c1 = 1.35
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def _ease_in_cubic(t: float) -> float:
    """Smooth exit easing curve."""
    return t * t * t


class FloatingHUD:
    """Ultra-smooth floating HUD: Anchored Bars -> Settle to String -> String Waves -> Stops Flat."""

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

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Fixed viewport dimensions (prevents Wayland window resizing jitter)
        self._win_w = max(180, self.config.hud_width or 190)
        self._win_h = max(42, self.config.hud_height or 46)
        self._pos_y = 30  # Top offset

    def start(self) -> None:
        """Start the HUD window in a background GUI thread."""
        if not self.config.show_hud or self._thread is not None:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Close HUD window."""
        self._running = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    def show_listening(self) -> None:
        """Trigger entering animation; shows dynamic audio-reactive vertical bars."""
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
            self._morph_progress = 0.0  # Initiates bar -> flat string -> wave morph
            if self._visibility == "hidden":
                self._visibility = "entering"
        self._trigger_update()

    def show_done(self, message: str = "✓ Injected") -> None:
        """Damp wave oscillations until string stops completely flat, then exit."""
        with self._lock:
            self._state = "done"
            self._done_decay = 1.0
        self._trigger_update()

        # Hold for wave to settle and stop flat (~800ms) then gracefully exit
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
        """Update live audio level (RMS) with smooth dynamic response."""
        with self._lock:
            target = max(0.15, min(1.0, level * 10.0))
            self._target_audio_level = target

    def _trigger_update(self) -> None:
        if self._root and self._running:
            try:
                self._root.after(0, self._render_frame)
            except Exception:
                pass

    def _run_gui(self) -> None:
        """Internal Tkinter GUI loop with stable 60 FPS rendering."""
        try:
            self._root = tk.Tk()
            self._root.title("Spic Wave")
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)

            screen_w = self._root.winfo_screenwidth()
            pos_x = (screen_w - self._win_w) // 2

            self._root.geometry(f"{self._win_w}x{self._win_h}+{pos_x}+{self._pos_y}")
            self._root.configure(bg=HUD_SURFACE_BG)

            try:
                self._root.attributes("-alpha", 0.0)
            except Exception:
                pass

            self._canvas = tk.Canvas(
                self._root,
                width=self._win_w,
                height=self._win_h,
                bg=HUD_SURFACE_BG,
                highlightthickness=0,
            )
            self._canvas.pack(fill="both", expand=True)

            self._animate_loop()
            self._root.withdraw()
            self._root.mainloop()
        except Exception:
            pass

    def _animate_loop(self) -> None:
        """60 FPS morphing physics loop."""
        if not self._running or not self._root:
            return

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

        self._render_frame()

        if self._root:
            self._root.after(16, self._animate_loop)

    def _render_frame(self) -> None:
        """Render the fully-anchored morphing visualizer on the rounded glass window."""
        if not self._root or not self._canvas:
            return

        with self._lock:
            vis = self._visibility
            progress = self._anim_progress
            state = self._state
            level = self._audio_level
            phase = self._phase
            morph = self._morph_progress
            done_decay = self._done_decay

        if vis == "hidden":
            self._root.withdraw()
            return
        else:
            self._root.deiconify()

        # Dynamic Alpha
        if vis == "entering":
            curr_alpha = min(0.96, progress * 1.1)
            scale = max(0.4, min(1.04, 0.4 + 0.64 * _ease_out_back(progress)))
        elif vis == "exiting":
            eased = _ease_in_cubic(progress)
            curr_alpha = max(0.0, progress * 0.96)
            scale = max(0.3, eased)
        else:
            curr_alpha = 0.96
            scale = 1.0

        try:
            self._root.attributes("-alpha", curr_alpha)
        except Exception:
            pass

        self._canvas.delete("all")
        win_w = float(self._win_w)
        win_h = float(self._win_h)
        cy = win_h / 2.0

        w = win_w * scale
        h = win_h
        offset_x = (win_w - w) / 2.0
        offset_y = 0.0

        # =========================================================================
        # 1. Capsule Surface & Rounded Floating Window Geometry
        # =========================================================================
        outer_pts = self._get_capsule_polygon(offset_x + 1.0, offset_y + 1.0, offset_x + w - 1.0, offset_y + h - 1.0)
        self._canvas.create_polygon(
            outer_pts,
            fill=HUD_SURFACE_BG,
            outline=CAPSULE_GLOW_OUTLINE,
            width=2.5,
            smooth=False,
        )

        inner_pts = self._get_capsule_polygon(offset_x + 2.0, offset_y + 2.0, offset_x + w - 2.0, offset_y + h - 2.0)
        self._canvas.create_polygon(
            inner_pts,
            fill=HUD_SURFACE_BG,
            outline=CAPSULE_BORDER_COLOR,
            width=1.6,
            smooth=False,
        )

        # Exact physical frame anchors (seamless 0px gap to left & right border apexes)
        x_left_anchor = offset_x + 2.0
        x_right_anchor = offset_x + w - 2.0
        total_string_span = max(10.0, x_right_anchor - x_left_anchor)

        if total_string_span < 15.0:
            return

        def _edge_envelope(nx: float) -> float:
            """Smooth edge pinning so wave firmly anchors at x_left and x_right."""
            return math.sin(nx * math.pi) ** 0.85

        # =========================================================================
        # STATE 1: LISTENING (Pure Vertical Audio-Reactive Spectrum Bars Only)
        # =========================================================================
        if state == "listening":
            num_bars = 28
            bar_width = 3.0
            bar_pad_x = offset_x + 8.0
            bar_area_w = max(10.0, w - 16.0)
            bar_spacing = bar_area_w / float(num_bars)
            max_bar_h = (h * 0.72) * min(1.0, progress * 1.2)
            min_bar_h = 4.0

            for i in range(num_bars):
                nx = i / float(num_bars - 1)
                bx = bar_pad_x + (i + 0.5) * bar_spacing

                # Multi-band voice frequency harmonics across the whole spectrum
                freq_osc = (
                    math.sin(i * 1.05 - phase * 3.8) * 0.40 +
                    math.cos(i * 1.75 + phase * 2.6) * 0.35 +
                    math.sin(nx * 12.0 - phase * 4.6) * 0.25
                )
                harmonic = 0.50 + 0.50 * freq_osc

                # Audio-level dynamic reactivity for all bars
                dyn_h = min_bar_h + (max_bar_h - min_bar_h) * (level * 0.85 + 0.15) * harmonic
                dyn_h = max(min_bar_h, min(max_bar_h, dyn_h))

                self._canvas.create_line(
                    bx, cy - (dyn_h / 2.0), bx, cy + (dyn_h / 2.0),
                    fill=THEME_CYAN_CORE,
                    width=bar_width,
                    capstyle="round",
                )

        # =========================================================================
        # STATE 2: PROCESSING (Bars Settle into Middle -> Fully Anchored String Waves)
        # =========================================================================
        elif state == "processing":
            # Phase A: Bars settle vertically into the middle (morph: 0.0 -> 0.5)
            if morph <= 0.5:
                collapse_k = 1.0 - (morph / 0.5)  # 1.0 -> 0.0

                # 1. Continuous fully anchored baseline string
                self._canvas.create_line(
                    x_left_anchor, cy, x_right_anchor, cy,
                    fill=THEME_CYAN_CORE,
                    width=2.4,
                    smooth=True,
                )

                # 2. Draw bars across the full span compressing down into centerline
                if collapse_k > 0.05:
                    num_bars = 28
                    bar_pad_x = offset_x + 8.0
                    bar_area_w = max(10.0, w - 16.0)
                    bar_spacing = bar_area_w / float(num_bars)

                    for i in range(num_bars):
                        nx = i / float(num_bars - 1)
                        bx = bar_pad_x + (i + 0.5) * bar_spacing

                        freq_osc = math.sin(i * 1.05 - phase * 3.8) * 0.5 + math.cos(i * 1.75 + phase * 2.6) * 0.5
                        harmonic = 0.50 + 0.50 * freq_osc

                        bar_h = max(2.0, (h * 0.65) * collapse_k * harmonic)
                        self._canvas.create_line(
                            bx, cy - (bar_h / 2.0), bx, cy + (bar_h / 2.0),
                            fill=THEME_CYAN_GLOW,
                            width=2.8 * collapse_k,
                            capstyle="round",
                        )

            # Phase B: The fully anchored string waves from border to border (morph: 0.5 -> 1.0)
            else:
                wave_growth = (morph - 0.5) / 0.5  # 0.0 -> 1.0
                think_amp = (h * 0.28) * wave_growth * min(1.0, progress * 1.2)
                step = 2.0

                pts = []
                glow_pts = []
                for px in range(0, int(total_string_span) + 1, int(step)):
                    x = x_left_anchor + px
                    nx = px / total_string_span
                    env = _edge_envelope(nx)

                    y_wave = cy + math.sin(nx * 8.0 - phase * 3.6) * (think_amp * env)
                    pts.extend([x, y_wave])

                    y_glow = cy + math.sin(nx * 12.0 + phase * 2.8) * (think_amp * 0.65 * env)
                    glow_pts.extend([x, y_glow])

                # Ensure exact connection to the right border
                pts.extend([x_right_anchor, cy])
                glow_pts.extend([x_right_anchor, cy])

                if len(glow_pts) >= 4 and wave_growth > 0.3:
                    self._canvas.create_line(
                        glow_pts,
                        fill=THEME_CYAN_GLOW,
                        width=1.6,
                        smooth=True,
                    )
                if len(pts) >= 4:
                    self._canvas.create_line(
                        pts,
                        fill=THEME_CYAN_CORE,
                        width=2.4,
                        smooth=True,
                    )

        # =========================================================================
        # STATE 3: DONE (Anchored String Waves Damp Down Until Flat & Still)
        # =========================================================================
        elif state == "done":
            step = 2.0
            done_amp = (h * 0.28) * done_decay * min(1.0, progress)

            # While wave is damping down
            if done_decay > 0.06:
                pts = []
                glow_pts = []
                for px in range(0, int(total_string_span) + 1, int(step)):
                    x = x_left_anchor + px
                    nx = px / total_string_span
                    env = _edge_envelope(nx)

                    y_wave = cy + math.sin(nx * 8.0 - phase * 3.0) * (done_amp * env)
                    pts.extend([x, y_wave])

                    y_glow = cy + math.sin(nx * 12.0 + phase * 2.4) * (done_amp * 0.6 * env)
                    glow_pts.extend([x, y_glow])

                pts.extend([x_right_anchor, cy])
                glow_pts.extend([x_right_anchor, cy])

                if len(glow_pts) >= 4 and done_decay > 0.3:
                    self._canvas.create_line(glow_pts, fill=THEME_CYAN_GLOW, width=1.6, smooth=True)
                if len(pts) >= 4:
                    self._canvas.create_line(pts, fill=THEME_CYAN_CORE, width=2.4, smooth=True)

            # Once oscillations stop completely: Flat string firmly anchored to left and right borders
            else:
                self._canvas.create_line(
                    x_left_anchor, cy, x_right_anchor, cy,
                    fill=THEME_CYAN_CORE,
                    width=2.4,
                    smooth=True,
                )

    def _get_capsule_polygon(self, x1: float, y1: float, x2: float, y2: float, segments: int = 36) -> list[float]:
        """Compute exact high-density trigonometric circular arcs for a seamless capsule window."""
        h = max(2.0, y2 - y1)
        r = h / 2.0
        cx_r = max(x1 + r, x2 - r)
        cx_l = x1 + r
        cy = y1 + r

        pts: list[float] = []

        # Right Semicircle Cap (-pi/2 -> +pi/2)
        for i in range(segments + 1):
            theta = -math.pi / 2.0 + (math.pi * i / segments)
            pts.extend([cx_r + r * math.cos(theta), cy + r * math.sin(theta)])

        # Left Semicircle Cap (+pi/2 -> +3*pi/2)
        for i in range(segments + 1):
            theta = math.pi / 2.0 + (math.pi * i / segments)
            pts.extend([cx_l + r * math.cos(theta), cy + r * math.sin(theta)])

        return pts

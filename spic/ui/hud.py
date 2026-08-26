"""High-fidelity floating HUD with 60 FPS fluid harmonic waves and spring transitions."""

from __future__ import annotations

import math
import threading
import time
from typing import Literal, Optional
import tkinter as tk

from spic.config import UIConfig

HUD_SURFACE_BG = "#13141F"


def _ease_out_back(t: float) -> float:
    """Spring overshoot easing curve."""
    c1 = 1.35
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def _ease_in_cubic(t: float) -> float:
    """Smooth exit easing curve."""
    return t * t * t


class FloatingHUD:
    """Ultra-smooth floating desktop HUD with 60 FPS fluid wave visualizer."""

    def __init__(self, config: UIConfig):
        self.config = config
        self._state: Literal["listening", "processing", "done"] = "listening"
        self._visibility: Literal["hidden", "entering", "visible", "exiting"] = "hidden"
        self._anim_progress = 0.0
        self._audio_level = 0.15
        self._target_audio_level = 0.15
        self._phase = 0.0
        self._done_progress = 0.0
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Fixed viewport dimensions (prevents Wayland window resizing jitter)
        self._win_w = max(180, self.config.hud_width or 190)
        self._win_h = max(42, self.config.hud_height or 46)
        self._pos_y = 30  # Screen top offset

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
        """Trigger entering animation into dynamic listening state."""
        with self._lock:
            self._state = "listening"
            self._audio_level = 0.25
            self._target_audio_level = 0.25
            self._visibility = "entering"
            if self._anim_progress <= 0.05:
                self._anim_progress = 0.0
        self._trigger_update()

    def show_processing(self) -> None:
        """Switch to thinking state with fluid neon cyan/violet flow waves."""
        with self._lock:
            self._state = "processing"
            if self._visibility == "hidden":
                self._visibility = "entering"
        self._trigger_update()

    def show_done(self, message: str = "✓ Injected") -> None:
        """Switch to done state (settling emerald pulse) then animate exit."""
        with self._lock:
            self._state = "done"
            self._done_progress = 1.0
        self._trigger_update()

        # Hold done wave for 650ms then gracefully exit
        def _delayed_exit():
            time.sleep(0.65)
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
            self._root.overrideredirect(True)  # Frameless
            self._root.attributes("-topmost", True)  # Always on top

            screen_w = self._root.winfo_screenwidth()
            pos_x = (screen_w - self._win_w) // 2

            # Set geometry ONCE to avoid Wayland buffer re-allocation lag
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
        """60 FPS transition and waveform tick."""
        if not self._running or not self._root:
            return

        with self._lock:
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

            self._audio_level += (self._target_audio_level - self._audio_level) * 0.22
            self._target_audio_level *= 0.96
            self._phase += 0.12

            if self._state == "done":
                self._done_progress = max(0.0, self._done_progress - 0.035)

        self._render_frame()

        if self._root:
            self._root.after(16, self._animate_loop)

    def _render_frame(self) -> None:
        """Render seamless capsule with smooth Bezier harmonic waves."""
        if not self._root or not self._canvas:
            return

        with self._lock:
            vis = self._visibility
            progress = self._anim_progress
            state = self._state
            level = self._audio_level
            phase = self._phase
            done_prog = self._done_progress

        if vis == "hidden":
            self._root.withdraw()
            return
        else:
            self._root.deiconify()

        # Update Alpha smoothly based on visibility
        if vis == "entering":
            curr_alpha = min(0.95, progress * 1.1)
            scale = max(0.4, min(1.04, 0.4 + 0.64 * _ease_out_back(progress)))
        elif vis == "exiting":
            eased = _ease_in_cubic(progress)
            curr_alpha = max(0.0, progress * 0.95)
            scale = max(0.3, eased)
        else:
            curr_alpha = 0.95
            scale = 1.0

        try:
            self._root.attributes("-alpha", curr_alpha)
        except Exception:
            pass

        self._canvas.delete("all")
        win_w = float(self._win_w)
        win_h = float(self._win_h)
        cy = win_h / 2.0

        # Dynamic internal scaling (rendered on canvas, avoiding window resize lag)
        w = win_w * scale
        h = win_h
        offset_x = (win_w - w) / 2.0
        offset_y = 0.0

        # State accent colors
        if state == "listening":
            border_color = "#FF3B30"
            border_glow = "#591B24"
        elif state == "processing":
            border_color = "#00F2FE"
            border_glow = "#10324F"
        elif state == "done":
            border_color = "#10B981"
            border_glow = "#123B28"
        else:
            border_color = "#3A3C52"
            border_glow = "#1E202E"

        # 1. Outer Glow Border
        outer_pts = self._get_capsule_polygon(offset_x + 1.0, offset_y + 1.0, offset_x + w - 1.0, offset_y + h - 1.0)
        self._canvas.create_polygon(
            outer_pts,
            fill=HUD_SURFACE_BG,
            outline=border_glow,
            width=2.5,
            smooth=False,
        )

        # 2. Crisp Primary Stroke
        inner_pts = self._get_capsule_polygon(offset_x + 2.0, offset_y + 2.0, offset_x + w - 2.0, offset_y + h - 2.0)
        self._canvas.create_polygon(
            inner_pts,
            fill=HUD_SURFACE_BG,
            outline=border_color,
            width=1.5,
            smooth=False,
        )

        # 3. Waveform Margins (Spans Full Width from Start to End)
        pad_x = offset_x + 6.0
        wave_w = max(10.0, w - 12.0)
        if wave_w < 15.0:
            return

        step = 2.0

        def _edge_envelope(nx: float) -> float:
            """Smooth edge softening only at extreme 6% edges for seamless cap anchoring."""
            if nx < 0.06:
                return math.sin((nx / 0.06) * (math.pi / 2.0))
            elif nx > 0.94:
                return math.sin(((1.0 - nx) / 0.06) * (math.pi / 2.0))
            return 1.0

        # =========================================================================
        # STATE 1: LISTENING WAVE (Crimson & Coral Audio Reactive Splines)
        # =========================================================================
        if state == "listening":
            max_amp = (h * 0.36) * max(0.20, level) * min(1.0, progress * 1.2)

            pts1, pts2, pts3 = [], [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = _edge_envelope(nx)

                y1 = cy + math.sin(nx * 10.0 - phase * 3.2) * (max_amp * env)
                pts1.extend([x, y1])

                y2 = cy + math.sin(nx * 14.0 + phase * 2.4) * math.cos(nx * 5.0 - phase * 1.6) * (max_amp * 0.78 * env)
                pts2.extend([x, y2])

                y3 = cy + math.sin(nx * 18.0 - phase * 4.0) * (max_amp * 0.48 * env)
                pts3.extend([x, y3])

            if len(pts3) >= 4:
                self._canvas.create_line(pts3, fill="#FFA07A", width=1.4, smooth=True)
            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#FF6B6B", width=1.8, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#FF3B30", width=2.8, smooth=True)

        # =========================================================================
        # STATE 2: THINKING WAVE (Neon Cyan & Violet Flow Ribbon)
        # =========================================================================
        elif state == "processing":
            think_amp = (h * 0.28) * min(1.0, progress * 1.2)

            pts1, pts2, pts3 = [], [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = _edge_envelope(nx)

                y1 = cy + math.sin(nx * 8.0 - phase * 3.6) * (think_amp * env)
                pts1.extend([x, y1])

                y2 = cy + math.sin(nx * 12.0 + phase * 2.8) * math.cos(nx * 6.0 - phase * 1.8) * (think_amp * 0.85 * env)
                pts2.extend([x, y2])

                y3 = cy + math.cos(nx * 16.0 - phase * 4.4) * (think_amp * 0.52 * env)
                pts3.extend([x, y3])

            if len(pts3) >= 4:
                self._canvas.create_line(pts3, fill="#A855F7", width=1.4, smooth=True)
            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#38BDF8", width=2.0, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#00F2FE", width=2.8, smooth=True)

        # =========================================================================
        # STATE 3: DONE WAVE (Emerald Settling Wave)
        # =========================================================================
        elif state == "done":
            done_amp = (h * 0.24) * done_prog * min(1.0, progress)

            pts1, pts2 = [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = _edge_envelope(nx)

                y1 = cy + math.sin(nx * 9.0 - phase * 2.0) * (done_amp * env)
                y2 = cy + math.cos(nx * 13.0 + phase * 1.6) * (done_amp * 0.62 * env)
                pts1.extend([x, y1])
                pts2.extend([x, y2])

            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#6EE7B7", width=1.6, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#10B981", width=2.6, smooth=True)

    def _get_capsule_polygon(self, x1: float, y1: float, x2: float, y2: float, segments: int = 24) -> list[float]:
        """Compute exact trigonometric circular arcs for a seamless capsule."""
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

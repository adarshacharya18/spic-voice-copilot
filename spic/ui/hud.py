"""High-fidelity floating HUD with fluid harmonic waves and spring enter/exit transitions."""

from __future__ import annotations

import math
import threading
import time
from typing import Literal, Optional
import tkinter as tk

from spic.config import UIConfig


def _ease_out_back(t: float) -> float:
    """Natural spring overshoot easing curve."""
    c1 = 1.25
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def _ease_in_cubic(t: float) -> float:
    """Smooth acceleration exit curve."""
    return t * t * t


class FloatingHUD:
    """Minimalist floating desktop pill with fluid harmonic waves and physics-based enter/exit animations."""

    def __init__(self, config: UIConfig):
        self.config = config
        self._state: Literal["listening", "processing", "done"] = "listening"
        self._visibility: Literal["hidden", "entering", "visible", "exiting"] = "hidden"
        self._anim_progress = 0.0  # 0.0 (hidden) to 1.0 (fully visible)
        self._audio_level = 0.1
        self._target_audio_level = 0.1
        self._phase = 0.0
        self._done_progress = 0.0
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Target layout constants
        self._base_width = max(160, self.config.hud_width or 170)
        self._base_height = max(38, self.config.hud_height or 42)
        self._target_y = 32  # Pixels below screen top
        self._spawn_y = -20   # Starting offset for drop animation

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
            # If entering from hidden, start progress from 0.0
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

        # Hold done state for 600ms then initiate smooth exit transition
        def _delayed_exit():
            time.sleep(0.6)
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
        """Internal Tkinter GUI loop with 60 FPS spring physics."""
        try:
            self._root = tk.Tk()
            self._root.title("Spic Wave")
            self._root.overrideredirect(True)  # Frameless
            self._root.attributes("-topmost", True)  # Always on top

            screen_w = self._root.winfo_screenwidth()
            win_w = self._base_width
            win_h = self._base_height
            pos_x = (screen_w - win_w) // 2

            self._root.geometry(f"{win_w}x{win_h}+{pos_x}+{self._spawn_y}")
            self._root.configure(bg="#0B0C10")

            try:
                self._root.attributes("-alpha", 0.0)
            except Exception:
                pass

            self._canvas = tk.Canvas(
                self._root,
                width=win_w,
                height=win_h,
                bg="#0B0C10",
                highlightthickness=0,
            )
            self._canvas.pack(fill="both", expand=True)

            # Start 60 FPS animation timer (16ms)
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
            # 1. Update Enter / Exit Transition Physics
            if self._visibility == "entering":
                # Enter transition duration ~180ms (step 0.09 per 16ms frame)
                self._anim_progress += 0.09
                if self._anim_progress >= 1.0:
                    self._anim_progress = 1.0
                    self._visibility = "visible"

            elif self._visibility == "exiting":
                # Exit transition duration ~220ms (step 0.075 per frame)
                self._anim_progress -= 0.075
                if self._anim_progress <= 0.0:
                    self._anim_progress = 0.0
                    self._visibility = "hidden"

            # 2. Audio Level LERP & Wave Phase
            self._audio_level += (self._target_audio_level - self._audio_level) * 0.25
            self._target_audio_level *= 0.96
            self._phase += 0.12

            if self._state == "done":
                self._done_progress = max(0.0, self._done_progress - 0.035)

        self._render_frame()

        if self._root:
            self._root.after(16, self._animate_loop)

    def _render_frame(self) -> None:
        """Render pill with dynamic spring geometry and fluid wave states."""
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

        # =========================================================================
        # 1. Physics Geometry & Alpha Interpolation
        # =========================================================================
        screen_w = self._root.winfo_screenwidth()
        base_w = self._base_width
        base_h = self._base_height

        if vis == "entering":
            eased = _ease_out_back(progress)
            curr_y = int(self._spawn_y + (self._target_y - self._spawn_y) * eased)
            curr_alpha = min(0.95, progress * 1.1)
            scale_x = max(0.35, min(1.05, 0.35 + 0.7 * eased))
        elif vis == "exiting":
            eased = _ease_in_cubic(progress)
            curr_y = int(self._spawn_y + (self._target_y - self._spawn_y) * eased)
            curr_alpha = max(0.0, progress * 0.95)
            scale_x = max(0.25, eased)
        else:  # "visible"
            curr_y = self._target_y
            curr_alpha = 0.95
            scale_x = 1.0

        pos_x = (screen_w - base_w) // 2

        try:
            self._root.geometry(f"{base_w}x{base_h}+{pos_x}+{curr_y}")
            self._root.attributes("-alpha", curr_alpha)
        except Exception:
            pass

        self._canvas.delete("all")
        cy = base_h / 2.0

        # Dynamic pill width based on entrance/exit scale
        active_w = base_w * scale_x
        offset_x = (base_w - active_w) / 2.0

        # =========================================================================
        # 2. Pill Capsule Background
        # =========================================================================
        self._draw_pill_container(offset_x, 0, offset_x + active_w, base_h, state)

        # Padding for wave within scaled pill
        pad_x = offset_x + (16 * scale_x)
        wave_w = active_w - (32 * scale_x)
        if wave_w < 15:
            return

        step = 2.5

        # =========================================================================
        # STATE 1: LISTENING WAVE (Crimson / Coral Audio Reactive Splines)
        # =========================================================================
        if state == "listening":
            max_amp = (base_h * 0.38) * max(0.18, level) * min(1.0, progress * 1.2)

            pts1, pts2, pts3 = [], [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = math.sin(nx * math.pi) ** 1.5

                y1 = cy + math.sin(nx * 14.0 - phase * 3.0) * (max_amp * env)
                pts1.extend([x, y1])

                y2 = cy + math.sin(nx * 19.0 + phase * 2.2) * math.cos(nx * 6.0 - phase * 1.5) * (max_amp * 0.75 * env)
                pts2.extend([x, y2])

                y3 = cy + math.sin(nx * 26.0 - phase * 4.0) * (max_amp * 0.45 * env)
                pts3.extend([x, y3])

            if len(pts3) >= 4:
                self._canvas.create_line(pts3, fill="#FFA07A", width=1.5, smooth=True)
            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#FF6B6B", width=2.0, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#FF3B30", width=2.8, smooth=True)

        # =========================================================================
        # STATE 2: THINKING WAVE (Cyan / Violet Quantum Intelligence Flow)
        # =========================================================================
        elif state == "processing":
            think_amp = (base_h * 0.28) * min(1.0, progress * 1.2)

            pts1, pts2, pts3 = [], [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = math.sin(nx * math.pi) ** 1.4

                y1 = cy + math.sin(nx * 10.0 - phase * 3.5) * (think_amp * env)
                pts1.extend([x, y1])

                y2 = cy + math.sin(nx * 15.0 + phase * 2.8) * math.cos(nx * 8.0 - phase * 1.8) * (think_amp * 0.85 * env)
                pts2.extend([x, y2])

                y3 = cy + math.cos(nx * 22.0 - phase * 4.2) * (think_amp * 0.5 * env)
                pts3.extend([x, y3])

            if len(pts3) >= 4:
                self._canvas.create_line(pts3, fill="#A855F7", width=1.5, smooth=True)
            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#38BDF8", width=2.2, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#00F2FE", width=2.8, smooth=True)

        # =========================================================================
        # STATE 3: DONE WAVE (Emerald / Mint Settling Wave)
        # =========================================================================
        elif state == "done":
            done_amp = (base_h * 0.22) * done_prog * min(1.0, progress)

            pts1, pts2 = [], []
            for px in range(0, int(wave_w) + 1, int(step)):
                x = pad_x + px
                nx = px / wave_w
                env = math.sin(nx * math.pi) ** 1.6

                y1 = cy + math.sin(nx * 12.0 - phase * 1.8) * (done_amp * env)
                y2 = cy + math.cos(nx * 16.0 + phase * 1.4) * (done_amp * 0.6 * env)
                pts1.extend([x, y1])
                pts2.extend([x, y2])

            if len(pts2) >= 4:
                self._canvas.create_line(pts2, fill="#6EE7B7", width=1.8, smooth=True)
            if len(pts1) >= 4:
                self._canvas.create_line(pts1, fill="#10B981", width=2.6, smooth=True)

    def _draw_pill_container(self, x1: float, y1: float, x2: float, y2: float, state: str) -> None:
        """Draw a mathematically precise capsule container with seamless border and background alignment."""
        if x2 - x1 < 10:
            return

        # State-reactive glowing ambient border colors
        if state == "listening":
            border_color = "#FF453A"
            glow_outline = "#591B24"
        elif state == "processing":
            border_color = "#38BDF8"
            glow_outline = "#18324F"
        elif state == "done":
            border_color = "#10B981"
            glow_outline = "#15422D"
        else:
            border_color = "#3B3D54"
            glow_outline = "#1E202E"

        # Outer subtle ambient glow stroke
        outer_pts = self._get_capsule_polygon(x1 + 0.5, y1 + 0.5, x2 - 0.5, y2 - 0.5)
        self._canvas.create_polygon(
            outer_pts,
            fill="#0D0E15",
            outline=glow_outline,
            width=2.5,
            smooth=False,
        )

        # Crisp inner border and unified dark glass surface
        inner_pts = self._get_capsule_polygon(x1 + 1.5, y1 + 1.5, x2 - 1.5, y2 - 1.5)
        self._canvas.create_polygon(
            inner_pts,
            fill="#0D0E15",
            outline=border_color,
            width=1.5,
            smooth=False,
        )

    def _get_capsule_polygon(self, x1: float, y1: float, x2: float, y2: float, segments: int = 18) -> list[float]:
        """Compute exact trigonometric vertices for a pixel-perfect circular capsule."""
        h = max(2.0, y2 - y1)
        r = h / 2.0
        cx_r = max(x1 + r, x2 - r)
        cx_l = x1 + r
        cy = y1 + r

        pts: list[float] = []

        # 1. Right Semicircle Cap (-pi/2 -> +pi/2)
        for i in range(segments + 1):
            theta = -math.pi / 2.0 + (math.pi * i / segments)
            pts.extend([cx_r + r * math.cos(theta), cy + r * math.sin(theta)])

        # 2. Left Semicircle Cap (+pi/2 -> +3*pi/2)
        for i in range(segments + 1):
            theta = math.pi / 2.0 + (math.pi * i / segments)
            pts.extend([cx_l + r * math.cos(theta), cy + r * math.sin(theta)])

        return pts

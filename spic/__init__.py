"""Spic - The Native, Zero-Lag Linux Voice Copilot."""

import os
import sys

# Ensure system python-gi is always accessible
if "/usr/lib/python3/dist-packages" not in sys.path:
    sys.path.append("/usr/lib/python3/dist-packages")

# Set GDK_BACKEND to x11 so GNOME Mutter allows exact top-middle screen placement
os.environ.setdefault("GDK_BACKEND", "x11")

__version__ = "0.1.0"

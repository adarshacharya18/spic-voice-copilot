#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ⚙️ Configuring Linux /dev/uinput permissions for Spic"
echo "============================================================"
echo "This allows Spic to type directly into any Wayland or X11 window"
echo "as a native virtual hardware keyboard."
echo ""

# 1. Create udev rule for persistent access without root
UDEV_RULE='KERNEL=="uinput", GROUP="input", MODE="0660", TAG+="uaccess"'
echo "$UDEV_RULE" | sudo tee /etc/udev/rules.d/99-uinput.rules > /dev/null

# 2. Add current user to input group
sudo usermod -aG input "$USER"

# 3. Reload udev rules and grant group permission for current session
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo chgrp input /dev/uinput 2>/dev/null || true
sudo chmod 0660 /dev/uinput 2>/dev/null || true

echo ""
echo "✅ /dev/uinput permissions successfully configured (restricted to group 'input')!"
echo "You can now test text injection with: python3 -m spic.cli test-injection"
echo "============================================================"

#!/usr/bin/env bash
# ==============================================================================
# Spic Linux Voice Copilot - Automated & Interactive Installer
# Supports: Ubuntu, Debian, Fedora, Arch Linux
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo " 🎙️  SPIC LINUX VOICE COPILOT - SETUP & INSTALLATION"
echo "============================================================"
echo -e "${NC}"

# 1. Detect Package Manager
echo -e "${BLUE}[1/5] Checking System Audio & Build Dependencies...${NC}"
if command -v apt-get &>/dev/null; then
    echo " -> Detected Debian/Ubuntu package manager (apt)"
    sudo apt-get update -qq
    sudo apt-get install -y python3-pip python3-venv pipewire pipewire-audio-client-libraries libglib2.0-bin libgirepository1.0-dev libcairo2-dev pkg-config
elif command -v dnf &>/dev/null; then
    echo " -> Detected Fedora/RHEL package manager (dnf)"
    sudo dnf install -y python3-pip python3-virtualenv pipewire pipewire-utils glib2 gobject-introspection-devel cairo-gobject-devel pkgconf-pkg-config
elif command -v pacman &>/dev/null; then
    echo " -> Detected Arch Linux package manager (pacman)"
    sudo pacman -Sy --noconfirm python-pip python-virtualenv pipewire pipewire-audio glib2 gobject-introspection cairo pkgconf
else
    echo -e "${YELLOW}Warning: Unknown package manager. Please ensure pipewire and python3 are installed.${NC}"
fi

# 2. Virtual Environment Setup
echo -e "\n${BLUE}[2/5] Setting up Python Virtual Environment (.venv)...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# 3. Kernel /dev/uinput Hardware Permissions
echo -e "\n${BLUE}[3/5] Configuring Linux Kernel Hardware Permissions (/dev/uinput)...${NC}"
if [ -f "./scripts/setup_uinput.sh" ]; then
    bash ./scripts/setup_uinput.sh
fi

# 4. Optional Ollama / LLM Setup (Interactive Choice)
echo -e "\n${BLUE}[4/5] Smart Voice Copilot (Local LLM Setup)...${NC}"
echo "------------------------------------------------------------"
echo " Spic provides two dictation engines:"
echo "   • Fast Dictation (Ctrl+Alt+Space): 100% offline, zero dependencies, uses local Whisper STT."
echo "   • Smart Voice Copilot (Ctrl+Super+Space): Uses an LLM for conversational self-corrections."
echo "------------------------------------------------------------"

if command -v ollama &>/dev/null; then
    echo -e "${GREEN}✓ Ollama is detected on your system.${NC}"
    echo "Tip: You can choose and pull any model you prefer (e.g. 'ollama pull llama3.2:3b')."
    echo "Spic will not force a model download during installation."
else
    echo -e "${YELLOW}Ollama is NOT installed on your system.${NC}"
    echo "Choose how you want to handle Ollama for Smart Mode:"
    echo "  [1] Automatically install Ollama now via official install script"
    echo "  [2] I want to install Ollama manually myself"
    echo "  [3] Skip Ollama (Use Fast Mode / Cloud API / Rule Cleaner only)"
    echo ""
    read -rp "Select an option [1/2/3] (default: 3): " ollama_choice
    ollama_choice=${ollama_choice:-3}

    if [ "$ollama_choice" = "1" ]; then
        echo -e "\n${BLUE}Installing Ollama via official installer...${NC}"
        curl -fsSL https://ollama.com/install.sh | sh
        echo -e "${GREEN}✓ Ollama installed successfully.${NC}"
        echo -e "${YELLOW}Note: Model download is NOT forced. When ready, pull your preferred model:${NC}"
        echo "      ollama pull llama3.2:3b"
    elif [ "$ollama_choice" = "2" ]; then
        echo -e "\n${YELLOW}============================================================${NC}"
        echo -e "${YELLOW} ⏸️  MANUAL OLLAMA INSTALLATION REQUIRED${NC}"
        echo -e "${YELLOW}============================================================${NC}"
        echo "To install Ollama manually, run:"
        echo "   curl -fsSL https://ollama.com/install.sh | sh"
        echo "   (or visit https://ollama.com/download/linux)"
        echo ""
        echo "After installing Ollama, start the service and pull your preferred model:"
        echo "   ollama pull llama3.2:3b"
        echo ""
        echo "Then re-run this installation script:"
        echo "   ./scripts/install.sh"
        echo -e "${YELLOW}============================================================${NC}"
        exit 0
    else
        echo -e "${GREEN}✓ Skipped Ollama installation.${NC}"
        echo "  Fast Mode (Ctrl+Alt+Space) will work 100% offline out-of-the-box."
        echo "  Smart Mode will use the deterministic Fast Rule Cleaner (or your configured Cloud API key)."
    fi
fi

# 5. Global Shortcuts Setup
echo -e "\n${BLUE}[5/5] Registering Desktop Global Shortcuts...${NC}"
python3 -m spic.cli shortcuts --apply-defaults || true

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN} ✅ SPIC INSTALLATION COMPLETE!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo " You can now run Spic in either mode:"
echo ""
echo " 🧪 Option A: Test in Foreground (Inspect terminal logs, Ctrl+C to exit):"
echo "    ./scripts/run_daemon.sh"
echo ""
echo " 🚀 Option B: Enable Background Service (Starts automatically on PC boot):"
echo "    python3 -m spic.cli autostart --enable"
echo ""
echo " Global Shortcuts:"
echo "   • Ctrl + Alt + Space   -> Fast Voice Dictation (On-the-GO Streaming)"
echo "   • Ctrl + Super + Space -> Smart Voice Copilot (LLM Reasoning)"
echo "============================================================"

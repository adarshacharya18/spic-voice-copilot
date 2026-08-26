#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Cleanly stop any existing daemon instance before starting
pkill -f "python3 -m spic.cli start" 2>/dev/null || true
sleep 0.2

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

exec python3 -m spic.cli start "$@"

#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
#  Velocis Intelli Agent — Startup Script
# ─────────────────────────────────────────────────────────

set -e

cd "$(dirname "$0")"

echo ""
echo "  ██╗   ██╗███████╗██╗      ██████╗  ██████╗██╗███████╗"
echo "  ██║   ██║██╔════╝██║     ██╔═══██╗██╔════╝██║██╔════╝"
echo "  ██║   ██║█████╗  ██║     ██║   ██║██║     ██║███████╗"
echo "  ╚██╗ ██╔╝██╔══╝  ██║     ██║   ██║██║     ██║╚════██║"
echo "   ╚████╔╝ ███████╗███████╗╚██████╔╝╚██████╗██║███████║"
echo "    ╚═══╝  ╚══════╝╚══════╝ ╚═════╝  ╚═════╝╚═╝╚══════╝"
echo "  Intelli Agent — Powered by Cisco AI Defense"
echo ""

# ── Check .env exists ──────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "  ⚠  .env file not found!"
  echo "     Copy .env.example to .env and fill in your credentials."
  exit 1
fi

# ── Create virtualenv if needed ────────────────────────────
if [ ! -d "venv" ]; then
  echo "  📦  Creating virtual environment…"
  python3 -m venv venv
fi

# ── Activate venv ──────────────────────────────────────────
source venv/bin/activate

# ── Install / upgrade dependencies ────────────────────────
echo "  📦  Installing dependencies…"
pip install -q -r requirements.txt

# ── Start server ──────────────────────────────────────────
echo "  🚀  Starting Velocis Intelli Agent…"
echo ""
python main.py

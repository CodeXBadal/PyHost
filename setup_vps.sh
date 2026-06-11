#!/bin/bash
# PyHost VPS Setup Script
# Run this ONCE on the VPS before starting the bot with docker compose up
set -e

echo "=== PyHost VPS Setup ==="

# 1. Create host projects directory
mkdir -p /opt/pyhost/projects
echo "[✓] Created /opt/pyhost/projects"

# 2. Get docker group GID
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo "999")
echo "[✓] Docker socket GID = $DOCKER_GID"

# 3. Check if .env exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[!] Created .env from .env.example — EDIT IT NOW with your tokens!"
else
    echo "[✓] .env already exists"
fi

# 4. Auto-fill DOCKER_GID and HOST_PROJECTS_DIR in .env if not set
if ! grep -q "^DOCKER_GID=" .env; then
    echo "DOCKER_GID=$DOCKER_GID" >> .env
    echo "[✓] Added DOCKER_GID=$DOCKER_GID to .env"
fi
if ! grep -q "^HOST_PROJECTS_DIR=" .env; then
    echo "HOST_PROJECTS_DIR=/opt/pyhost/projects" >> .env
    echo "[✓] Added HOST_PROJECTS_DIR to .env"
fi

echo ""
echo "=== Setup complete! ==="
echo "Next steps:"
echo "  1. Edit .env with your BOT_TOKEN, ADMIN_IDS, ENCRYPTION_KEY etc."
echo "  2. Run: docker compose up -d --build"
echo "  3. Check logs: docker compose logs -f bot"

#!/bin/bash
# 🚀 1-Click Server Setup Script for Ghost Copilot
set -e

echo "=== Updating System & Installing Prerequisites ==="
if [ -x "$(command -v apt-get)" ]; then
    apt-get update -y
    apt-get install -y python3 python3-pip ffmpeg curl ufw
elif [ -x "$(command -v yum)" ]; then
    yum install -y epel-release
    yum install -y python3 python3-pip ffmpeg curl
fi

echo "=== Allowing Port 9471 in Firewall ==="
if [ -x "$(command -v ufw)" ]; then
    ufw allow 9471/tcp || true
fi

echo "=== Starting Ghost Copilot Server ==="
pkill -f "app.py" 2>/dev/null || true
nohup python3 app.py > copilot.log 2>&1 &

echo "=========================================================="
echo "✅ Ghost Copilot Server is RUNNING on port 9471!"
echo "Check logs with: tail -f copilot.log"
echo "Access HUD at:   http://$(curl -s ifconfig.me):9471"
echo "=========================================================="

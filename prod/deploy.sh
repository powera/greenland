#!/bin/bash
# Deployment script for Barsukas production server
# Run as greenland user

set -e

REPO_DIR="/home/greenland/ROOT"
VENV_DIR="$REPO_DIR/venv"

cd "$REPO_DIR"

echo "Pulling latest changes..."
git pull

echo "Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install -q -r requirements.txt

echo "Restarting barsukas service..."
sudo systemctl restart barsukas.service

echo "Checking service status..."
sleep 2
systemctl status barsukas.service --no-pager

echo ""
echo "Recent logs:"
journalctl -u barsukas.service -n 10 --no-pager

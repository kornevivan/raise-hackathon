#!/usr/bin/env bash
# Self-updater: pull the latest main and rebuild only when it changed.
# Installed as a cron job (every 2 min) so pushes to GitHub deploy themselves.
set -e
cd /opt/cs || exit 0
git fetch origin main --quiet || exit 0
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
echo "[$(date -u +%FT%TZ)] update $LOCAL -> $REMOTE" >> /var/log/cs-autoupdate.log
git reset --hard origin/main >> /var/log/cs-autoupdate.log 2>&1
docker compose up -d --build >> /var/log/cs-autoupdate.log 2>&1
echo "[$(date -u +%FT%TZ)] rebuilt" >> /var/log/cs-autoupdate.log

#!/usr/bin/env bash
# Deploy the Trade app. Run this ON the production server.
#
#  1. Updates the app code from git
#  2. Syncs Python dependencies
#  3. Restarts the PM2 "trade" process (see ecosystem.config.js)

set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/var/www/html/trade}"
BRANCH="${DEPLOY_BRANCH:-main}"

cd "${DEPLOY_PATH}"

echo "==> Updating to '${BRANCH}'..."
git fetch origin
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "==> Syncing dependencies..."
. .venv/bin/activate
uv sync --frozen

echo "==> Restarting PM2 app 'trade'..."
pm2 restart trade --update-env

echo "==> Deployment complete."
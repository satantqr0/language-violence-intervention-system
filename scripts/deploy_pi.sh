#!/bin/bash
# Deploy the project to Raspberry Pi 5.
#
# Defaults target the user's Pi:
#   PI_HOST=192.168.1.100
#   PI_USER=pi
#
# Passwords are intentionally not stored in this repository. For password auth:
#   export SSHPASS='your ssh password'
#   export SUDO_PASSWORD='your sudo password'
#   bash scripts/deploy_pi.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_HOST="${PI_HOST:-192.168.1.100}"
PI_USER="${PI_USER:-pi}"
REMOTE_DIR="${REMOTE_DIR:-/home/${PI_USER}/language-violence-intervention-system}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-1}"
START_SERVICES="${START_SERVICES:-1}"
ENABLE_AUDIO_UPLOAD="${ENABLE_AUDIO_UPLOAD:-0}"
ENABLE_AUDIO_CLEANUP="${ENABLE_AUDIO_CLEANUP:-1}"
SSH_KEY="${SSH_KEY:-}"
WEB_TLS_IP="${WEB_TLS_IP:-${PI_HOST}}"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
SSH_CMD=(ssh "${SSH_OPTS[@]}")
RSYNC_RSH="ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30"

if [ -n "$SSH_KEY" ]; then
    SSH_CMD=(ssh -i "$SSH_KEY" "${SSH_OPTS[@]}")
    RSYNC_RSH="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30"
elif [ -n "${SSHPASS:-}" ]; then
    SSH_CMD=(sshpass -e ssh "${SSH_OPTS[@]}")
    RSYNC_RSH="sshpass -e ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30"
fi

echo "Deploying to ${PI_USER}@${PI_HOST}:${REMOTE_DIR}"

"${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "mkdir -p '${REMOTE_DIR}'"

rsync -az --delete \
    -e "$RSYNC_RSH" \
    --exclude ".DS_Store" \
    --exclude ".env" \
    --exclude "venv/" \
    --exclude "__pycache__/" \
    --exclude "*.pyc" \
    --exclude "audio/*" \
    --exclude "data/*" \
    --exclude "logs/*.csv" \
    --exclude "logs/*.jsonl" \
    --exclude "logs/event_marks.json" \
    --exclude "models/*" \
    "${PROJECT_DIR}/" "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/"

"${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "cd '${REMOTE_DIR}' && chmod +x scripts/*.sh scripts/audio_smb_uploader.py"

REMOTE_SETUP_CMD="cd '${REMOTE_DIR}' && bash scripts/setup.sh"
if [ -n "${SUDO_PASSWORD:-}" ]; then
    printf '%s\n' "$SUDO_PASSWORD" | "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "sudo -S -v && ${REMOTE_SETUP_CMD}"
else
    "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "$REMOTE_SETUP_CMD"
fi

if [ "$INSTALL_SYSTEMD" = "1" ]; then
    REMOTE_INSTALL_CMD="cd '${REMOTE_DIR}' && sudo -S env SERVICE_USER='${PI_USER}' PROJECT_DIR='${REMOTE_DIR}' START_SERVICES='${START_SERVICES}' ENABLE_AUDIO_UPLOAD='${ENABLE_AUDIO_UPLOAD}' ENABLE_AUDIO_CLEANUP='${ENABLE_AUDIO_CLEANUP}' WEB_TLS_IP='${WEB_TLS_IP}' bash scripts/install_systemd.sh"
    if [ -n "${SUDO_PASSWORD:-}" ]; then
        printf '%s\n' "$SUDO_PASSWORD" | "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "$REMOTE_INSTALL_CMD"
    else
        "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "cd '${REMOTE_DIR}' && sudo env SERVICE_USER='${PI_USER}' PROJECT_DIR='${REMOTE_DIR}' START_SERVICES='${START_SERVICES}' ENABLE_AUDIO_UPLOAD='${ENABLE_AUDIO_UPLOAD}' ENABLE_AUDIO_CLEANUP='${ENABLE_AUDIO_CLEANUP}' WEB_TLS_IP='${WEB_TLS_IP}' bash scripts/install_systemd.sh"
    fi
fi

echo ""
echo "Deployment finished."
echo "Web console: https://${PI_HOST}:5000"
echo "Remote dir: ${REMOTE_DIR}"

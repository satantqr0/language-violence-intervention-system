#!/bin/bash
# Compatibility entry point. Credentials belong in the environment, never here.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_DIR}/.env"
    set +a
fi

if [ -n "${PI_PASS:-}" ] && [ -z "${SSHPASS:-}" ]; then
    export SSHPASS="${PI_PASS}"
fi
if [ -z "${SUDO_PASSWORD:-}" ] && command -v security >/dev/null 2>&1; then
    SUDO_PASSWORD="$(security find-generic-password -w \
        -a "${PI_USER:-pi}@${PI_HOST:-192.168.1.100}" \
        -s "language-violence-pi-sudo" 2>/dev/null || true)"
fi
export SUDO_PASSWORD="${SUDO_PASSWORD:-${PI_PASS:-}}"

exec bash "${PROJECT_DIR}/scripts/deploy_pi.sh" "$@"

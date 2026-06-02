#!/bin/bash
# Kept for existing shortcuts: run the secured deployment flow.

set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "${PROJECT_DIR}/scripts/deploy.sh" "$@"

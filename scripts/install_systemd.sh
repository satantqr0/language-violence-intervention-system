#!/bin/bash
# Install systemd units on Raspberry Pi.

set -euo pipefail

SERVICE_USER="${SERVICE_USER:-pi}"
PROJECT_DIR="${PROJECT_DIR:-/home/${SERVICE_USER}/language-violence-intervention-system}"
PYTHON_BIN="${PROJECT_DIR}/venv/bin/python"
ENV_FILE="${PROJECT_DIR}/.env"
START_SERVICES="${START_SERVICES:-1}"
ENABLE_AUDIO_UPLOAD="${ENABLE_AUDIO_UPLOAD:-0}"
ENABLE_AUDIO_CLEANUP="${ENABLE_AUDIO_CLEANUP:-1}"
WEB_TLS_IP="${WEB_TLS_IP:-192.168.1.100}"
TLS_DIR="${PROJECT_DIR}/data/tls"
TLS_CERT="${TLS_DIR}/web-console.crt"
TLS_KEY="${TLS_DIR}/web-console.key"

install -d -m 0755 /etc/systemd/system
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0700 "${TLS_DIR}"
if [ ! -s "${TLS_CERT}" ] || [ ! -s "${TLS_KEY}" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -subj "/CN=${WEB_TLS_IP}" \
        -addext "subjectAltName=IP:${WEB_TLS_IP}" \
        -keyout "${TLS_KEY}" -out "${TLS_CERT}" >/dev/null 2>&1
    chown "${SERVICE_USER}:${SERVICE_USER}" "${TLS_CERT}" "${TLS_KEY}"
    chmod 0600 "${TLS_CERT}" "${TLS_KEY}"
fi

cat >/etc/systemd/system/language-violence-intervention-system.service <<EOF
[Unit]
Description=Language Violence Detector Main Service
Wants=network-online.target
After=network-online.target sound.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${ENV_FILE}
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${PROJECT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStartPre=/bin/sleep 8
ExecStart=${PYTHON_BIN} ${PROJECT_DIR}/src/main.py
Restart=on-failure
RestartSec=5
SupplementaryGroups=audio
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/language-violence-web.service <<EOF
[Unit]
Description=Language Violence Detector Web Console
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${ENV_FILE}
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${PROJECT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${PROJECT_DIR}/venv/bin/gunicorn --workers 1 --threads 4 --timeout 120 --certfile ${TLS_CERT} --keyfile ${TLS_KEY} --bind 0.0.0.0:5000 web_app:app
Restart=on-failure
RestartSec=5
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/language-violence-audio-cleanup.service <<EOF
[Unit]
Description=Clean old Language Violence Detector audio files

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${PYTHON_BIN} ${PROJECT_DIR}/scripts/cleanup_audio.py
EOF

cat >/etc/systemd/system/language-violence-audio-cleanup.timer <<EOF
[Unit]
Description=Run Language Violence Detector audio cleanup daily

[Timer]
OnBootSec=15min
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat >/etc/systemd/system/language-violence-audio-upload.service <<EOF
[Unit]
Description=Upload Language Violence Detector audio clips to SMB
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${PYTHON_BIN} ${PROJECT_DIR}/scripts/audio_smb_uploader.py
NoNewPrivileges=true
EOF

cat >/etc/systemd/system/language-violence-audio-upload.timer <<EOF
[Unit]
Description=Run Language Violence Detector audio SMB uploader every 2 hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=2h
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat >/etc/sudoers.d/language-violence-intervention-system <<EOF
${SERVICE_USER} ALL=(root) NOPASSWD: /bin/systemctl start language-violence-intervention-system.service, /bin/systemctl stop language-violence-intervention-system.service, /bin/systemctl restart language-violence-intervention-system.service, /bin/systemctl status language-violence-intervention-system.service
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start language-violence-intervention-system.service, /usr/bin/systemctl stop language-violence-intervention-system.service, /usr/bin/systemctl restart language-violence-intervention-system.service, /usr/bin/systemctl status language-violence-intervention-system.service
EOF
chmod 0440 /etc/sudoers.d/language-violence-intervention-system
visudo -cf /etc/sudoers.d/language-violence-intervention-system

systemctl daemon-reload

# Stop legacy manually-started processes that would otherwise keep port 5000 busy.
pkill -u "${SERVICE_USER}" -f "${PROJECT_DIR}/web_app.py" 2>/dev/null || true
pkill -u "${SERVICE_USER}" -f "python -u web_app.py" 2>/dev/null || true

systemctl enable language-violence-web.service language-violence-intervention-system.service

if [ "$ENABLE_AUDIO_CLEANUP" = "1" ]; then
    systemctl enable language-violence-audio-cleanup.timer
fi

if [ "$ENABLE_AUDIO_UPLOAD" = "1" ]; then
    systemctl enable language-violence-audio-upload.timer
fi

if [ "$START_SERVICES" = "1" ]; then
    systemctl restart language-violence-web.service language-violence-intervention-system.service
    if [ "$ENABLE_AUDIO_UPLOAD" = "1" ]; then
        systemctl restart language-violence-audio-upload.timer
    fi
    if [ "$ENABLE_AUDIO_CLEANUP" = "1" ]; then
        systemctl restart language-violence-audio-cleanup.timer
    fi
fi

systemctl --no-pager --full status language-violence-web.service language-violence-intervention-system.service language-violence-audio-cleanup.timer || true

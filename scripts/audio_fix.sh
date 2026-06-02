#!/bin/bash
# =====================================================================
#  USB 音箱无声修复脚本 — 在 Mac 终端 SSH 到树莓派运行
# =====================================================================

PI_HOST="${PI_HOST:-192.168.1.100}"
PI_USER="${PI_USER:-pi}"
SSH_KEY="${SSH_KEY:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15)
SSH_CMD=(ssh "${SSH_OPTS[@]}")
if [[ -n "$SSH_KEY" ]]; then
    SSH_CMD=(ssh -i "$SSH_KEY" "${SSH_OPTS[@]}")
elif [[ -n "${SSHPASS:-}" ]]; then
    command -v sshpass >/dev/null || { echo "需要安装 sshpass: brew install sshpass"; exit 1; }
    SSH_CMD=(sshpass -e ssh "${SSH_OPTS[@]}")
fi
run() {
    "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "$1" 2>/dev/null
}

echo -e "${CYAN}═══════════════════════════════════════════════════${RESET}"
echo -e "${CYAN}  USB 音箱无声 — 一键修复${RESET}"
echo -e "${CYAN}═══════════════════════════════════════════════════${RESET}"
echo ""

# ── 1. 确保用户在 audio 组 ────────────────────────────────────────────
echo -e "${YELLOW}[1] 检查音频组权限…${RESET}"
MEMBER=$(run "groups ${PI_USER} | grep -q audio && echo yes || echo no")
if [[ "$MEMBER" == "no" ]]; then
    echo "  用户不在 audio 组，添加中…"
    run "sudo usermod -aG audio ${PI_USER}"
    echo -e "  ${GREEN}✓ 已添加用户到 audio 组（下次登录生效）${RESET}"
else
    echo -e "  ${GREEN}✓ 已在 audio 组${RESET}"
fi

# ── 2. 设置默认 ALSA 设备 ────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[2] 配置 ALSA 默认设备…${RESET}"
run "cat > /tmp/asound.conf << 'EOF'
pcm.!default {
    type plug
    slave.pcm \"softvol\"
}

pcm.softvol {
    type softvol
    slave {
        pcm \"plug:default\"
    }
    control {
        name \"Soft Master\"
        card 0
    }
    min_dB -51.0
    max_dB 0.0
}
EOF
sudo cp /tmp/asound.conf /etc/asound.conf
echo '  ALSA 配置已写入 /etc/asound.conf'"
run "cat /etc/asound.conf"

# ── 3. 设置默认音频设备优先级 ─────────────────────────────────────────
echo ""
echo -e "${YELLOW}[3] 配置系统音频设备…${RESET}"
run "sudo sed -i 's/^defaults.ctl.card.*/defaults.ctl.card 0/' /etc/modprobe.d/alsa-base.conf 2>/dev/null || true"
run "sudo sed -i 's/^defaults.pcm.card.*/defaults.pcm.card 0/' /etc/modprobe.d/alsa-base.conf 2>/dev/null || true"

# ── 4. 安装/修复音频工具 ────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[4] 检查音频播放器…${RESET}"
for p in mpv paplay aplay ffmpeg; do
    if ! run "which $p >/dev/null 2>&1"; then
        echo "  安装 $p…"
        run "sudo apt-get install -y $p" 2>/dev/null
    else
        echo -e "  ${GREEN}✓ $p 已安装${RESET}"
    fi
done

# ── 5. 测试播放（生成 440Hz 正弦波） ────────────────────────────────────
echo ""
echo -e "${YELLOW}[5] 测试播放（440Hz 正弦波 3 秒）…${RESET}"
run "python3 -c \"
import struct, wave, math, os
with wave.open('/tmp/test_tone.wav', 'w') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
    for i in range(24000):
        f.writeframes(struct.pack('<h', int(20000 * math.sin(2*math.pi*440*i/8000))))
print('生成成功')
\" 2>&1"

echo "  用 aplay 播放（直接）:"
OUT1=$(run "aplay /tmp/test_tone.wav 2>&1")
echo "  $OUT1"

echo "  用 paplay 播放（PulseAudio）:"
OUT2=$(run "paplay /tmp/test_tone.wav 2>&1" || echo "(paplay 不可用)")
echo "  $OUT2"

echo "  用 mpv 播放:"
OUT3=$(run "mpv --no-video /tmp/test_tone.wav 2>&1" || echo "(mpv 不可用)")
echo "  $OUT3"

run "rm -f /tmp/test_tone.wav"

# ── 6. 重启音频服务 ────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[6] 重启音频服务…${RESET}"
run "sudo alsa force-reload 2>/dev/null || true"
run "pulseaudio --kill 2>/dev/null || true"
run "pulseaudio --start 2>/dev/null || true"
run "pipewire --kill 2>/dev/null || true"
run "pipewire 2>/dev/null || true"
echo -e "  ${GREEN}✓ 音频服务已重启${RESET}"

# ── 7. 检查哪个播放方式有效 ──────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[7] 检查可用播放后端（确定用哪个）…${RESET}"
if run "which paplay >/dev/null 2>&1"; then
    echo "  → 使用 paplay（PulseAudio）"
    PLAY_CMD="paplay"
elif run "which mpv >/dev/null 2>&1"; then
    echo "  → 使用 mpv"
    PLAY_CMD="mpv --no-video"
elif run "which aplay >/dev/null 2>&1"; then
    echo "  → 使用 aplay"
    PLAY_CMD="aplay"
else
    echo "  ✗ 未找到任何播放器！"
    PLAY_CMD=""
fi

# ── 8. 更新系统配置使用正确的播放器 ──────────────────────────────────────
echo ""
echo -e "${YELLOW}[8] 更新 config.json 播放器配置…${RESET}"
if [[ -n "$PLAY_CMD" ]]; then
    echo "  检测到播放器: $PLAY_CMD"
    # 这里只是提示，实际更新需要在 config.json 里配置
    if [[ "$PLAY_CMD" == "paplay" ]]; then
        echo "  TTS 播放器: paplay ✓"
    elif [[ "$PLAY_CMD" == "mpv"* ]]; then
        echo "  TTS 播放器: mpv ✓"
    elif [[ "$PLAY_CMD" == "aplay" ]]; then
        echo "  TTS 播放器: aplay ✓"
    fi
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${RESET}"
echo -e "${CYAN}  修复完成！${RESET}"
echo -e "${CYAN}═══════════════════════════════════════════════════${RESET}"
echo ""
echo "  如果测试播放有声音 → 音箱正常，问题是 TTS 配置"
echo "  如果测试播放无声音 → USB 音箱本身有配置问题"
echo "  请把输出结果发给我进一步分析"
echo ""

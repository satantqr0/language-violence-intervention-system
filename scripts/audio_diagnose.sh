#!/bin/bash
# =====================================================================
#  USB 音箱无声诊断脚本 — 在 Mac 终端运行
# =====================================================================

PI_HOST="${PI_HOST:-192.168.1.100}"
PI_USER="${PI_USER:-pi}"
SSH_KEY="${SSH_KEY:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

echo ""
echo -e "${YELLOW}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${YELLOW}║   USB 音箱无声诊断${RESET}"
echo -e "${YELLOW}╚══════════════════════════════════════════════╝${RESET}"
echo ""

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ConnectTimeout=10)
SSH_CMD=(ssh "${SSH_OPTS[@]}")
if [[ -n "$SSH_KEY" ]]; then
    SSH_CMD=(ssh -i "$SSH_KEY" "${SSH_OPTS[@]}")
elif [[ -n "${SSHPASS:-}" ]]; then
    command -v sshpass >/dev/null || { echo -e "${RED}[需要] 请安装 sshpass${RESET}"; exit 1; }
    SSH_CMD=(sshpass -e ssh "${SSH_OPTS[@]}")
fi

run() {
    "${SSH_CMD[@]}" "${PI_USER}@${PI_HOST}" "$1" 2>/dev/null
}

echo -e "${GREEN}[1/8] 检查 USB 设备是否识别${RESET}"
USB_AUDIO=$(run "lsusb | grep -iE 'audio|sound|usb|speaker|audio codec' || echo '未找到 USB 音频设备'")
echo "$USB_AUDIO"

echo ""
echo -e "${GREEN}[2/8] 检查声卡列表${RESET}"
run "aplay -l 2>&1 || echo 'aplay 不可用'"
run "cat /proc/asound/cards 2>/dev/null || echo '/proc/asound 不存在'"

echo ""
echo -e "${GREEN}[3/8] ALSA 默认设备${RESET}"
run "cat /etc/asound.conf 2>/dev/null; cat ~/.asoundrc 2>/dev/null || echo '无自定义 ALSA 配置'"

echo ""
echo -e "${GREEN}[4/8] PulseAudio / PipeWire 状态${RESET}"
PW_SINK=$(run "pw-cli list-objects | grep -i 'node.name' | head -10 2>/dev/null || echo 'PipeWire 未运行'")
echo "$PW_SINK"
PA_SINK=$(run "pactl list sinks short 2>/dev/null || echo 'PulseAudio sinks 无输出'")
echo "$PA_SINK"

echo ""
echo -e "${GREEN}[5/8] 用户音频组权限${RESET}"
run "groups; id; groups | grep -q audio && echo '✓ 在 audio 组' || echo '✗ 不在 audio 组'"

echo ""
echo -e "${GREEN}[6/8] 音量状态${RESET}"
run "amixer scontrols 2>/dev/null | head -5 || echo 'amixer 不可用'"
run "amixer get Master 2>/dev/null | tail -3 || echo '无法读取音量'"

echo ""
echo -e "${GREEN}[7/8] 播放器可用性${RESET}"
for p in aplay mpv paplay ffmpeg; do
    if run "which $p >/dev/null 2>&1"; then
        ver=$(run "$p --version 2>/dev/null | head -1 || echo "已安装")
        echo -e "  ✓ $p: $ver"
    else
        echo -e "  ✗ $p: 未安装"
    fi
done

echo ""
echo -e "${GREEN}[8/8] TTS 测试（用 aplay）${RESET}"
TEST_WAV="/tmp/test_tone.wav"
run "python3 -c \"
import struct, wave, math
with wave.open('${TEST_WAV}', 'w') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
    for i in range(8000): f.writeframes(struct.pack('<h', int(16000 * math.sin(2*math.pi*440*i/8000))))
print('生成测试音成功')
\" 2>&1"
run "echo '--- 用 aplay 播放 ---' && aplay -D plughw:Device ${TEST_WAV} 2>&1 || aplay ${TEST_WAV} 2>&1"
run "echo '--- 用 paplay 播放 ---' && paplay ${TEST_WAV} 2>&1 || echo 'paplay 不可用'"
run "echo '--- 用 mpv 播放 ---' && mpv --no-video ${TEST_WAV} 2>&1 || echo 'mpv 不可用'"
run "rm -f ${TEST_WAV}"

echo ""
echo -e "${GREEN}诊断完成，请把输出发给助手分析${RESET}"

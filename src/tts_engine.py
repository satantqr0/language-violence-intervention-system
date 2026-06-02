#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主动语音干预模块
本地Edge TTS引擎生成干预语音 + 智能设备检测
自动选择 USB 音箱作为输出设备
"""

import os
import re
import time
import subprocess
import shutil
from typing import Dict, List, Optional
from pathlib import Path
import threading


def order_alsa_playback_devices(aplay_output: str) -> List[str]:
    """Order ALSA outputs so a speaker is preferred over a microphone array jack."""
    candidates = []
    for order, line in enumerate(aplay_output.splitlines()):
        lower = line.lower()
        if "card" not in lower or "hdmi" in lower or "vc4" in lower:
            continue
        match = re.search(r"card\s+\d+:\s*([^\s\[]+)", line)
        if not match:
            continue
        score = 0
        if any(tag in lower for tag in ("speaker", "headphone", "dac", "br17", "jieli")):
            score += 100
        if any(tag in lower for tag in ("microphone", " mic ", "array", "respeaker")):
            score -= 100
        candidates.append((score, -order, f"plughw:CARD={match.group(1)},DEV=0"))
    candidates.sort(reverse=True)
    return [device for _score, _order, device in candidates]


def detect_alsa_playback_devices() -> List[str]:
    try:
        result = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
        return order_alsa_playback_devices(result.stdout)
    except Exception:
        return []


class TTSEngine:
    """TTS语音合成引擎"""

    INTERVENTION_TEXTS = {
        "high": "请冷静一下，换一种表达方式可能会有更好的效果。",
        "medium": "也许我们可以换个角度看这个问题。",
        "low": "希望你们能相互理解，好好沟通。"
    }

    def __init__(self, use_edge_tts: bool = True, output_dir: str = None,
                 voice: str = "zh-CN-XiaoxiaoNeural"):
        self.use_edge_tts = use_edge_tts
        self.output_dir = Path(output_dir) if output_dir else Path("/tmp/tts_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.edge_tts_available = False
        self.is_speaking = False
        self.voice = voice
        self.rate = "+10%"
        self.volume = "+20%"
        self.output_device = os.getenv("VD_AUDIO_OUTPUT_DEVICE", "").strip()
        # 检测到的播放设备和命令
        self._play_cmd: Optional[list] = None
        self._detected_device_name: str = "未知"

    def load(self):
        print("   初始化TTS引擎...")
        self._detect_audio_device()

        if self.use_edge_tts:
            if self._check_edge_tts():
                self.edge_tts_available = True
                print(f"   Edge TTS就绪 (输出设备: {self._detected_device_name})")
            else:
                print("   Edge TTS不可用，降级到模拟模式")
        else:
            print("   使用模拟TTS模式（无声音输出）")

        if not self.edge_tts_available:
            print("   TTS运行于模拟模式 (edge-tts未安装)")

    def _detect_audio_device(self):
        """
        自动检测最佳音频输出设备。
        优先级：USB 音箱 > 3.5mm 音频口 > HDMI > 系统默认
        """
        detected = None
        dev_name = "系统默认"
        alsa_devices = detect_alsa_playback_devices()

        # 1. Prefer an explicitly configured ALSA playback device.
        if self.output_device and shutil.which("mpv"):
            detected = [
                "mpv", "--no-video", "--really-quiet",
                f"--audio-device=alsa/{self.output_device}"
            ]
            dev_name = f"ALSA {self.output_device} (configured)"

        # 2. 尝试 paplay (PulseAudio / PipeWire)
        if not detected and shutil.which("paplay"):
            # 检查是否有可用的 sink
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=5
            )
            sinks = []
            for order, line in enumerate(result.stdout.strip().split("\n")):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        sink_name = parts[1]
                        # 排除 HDMI 和 Dummy
                        if "hdmi" not in sink_name.lower() and "dummy" not in sink_name.lower():
                            lower = line.lower()
                            score = 100 if any(tag in lower for tag in ("speaker", "headphone", "dac", "br17", "jieli")) else 0
                            if any(tag in lower for tag in ("microphone", " mic ", "array", "respeaker")):
                                score -= 100
                            sinks.append((score, -order, sink_name))
            if sinks:
                sinks.sort(reverse=True)
                sink_name = sinks[0][2]
                detected = ["paplay", f"--device={sink_name}"]
                dev_name = f"PulseAudio: {sink_name}"
            if not detected:
                # fallback：用默认 sink
                default = subprocess.run(
                    ["pactl", "get-default-sink"],
                    capture_output=True, text=True, timeout=5
                )
                default_sink = default.stdout.strip()
                if default_sink and "dummy" not in default_sink.lower():
                    detected = ["paplay", default_sink]
                    dev_name = f"PulseAudio默认: {default_sink}"

        # 3. 尝试 mpv，使用实际暴露播放能力的非 HDMI ALSA 设备。
        if not detected and shutil.which("mpv") and alsa_devices:
            alsa_device = alsa_devices[0]
            detected = [
                "mpv", "--no-video", "--really-quiet",
                f"--audio-device=alsa/{alsa_device}"
            ]
            dev_name = f"ALSA {alsa_device} (mpv)"

        # 4. 尝试 aplay + 指定 card（仅适用于 wav）。
        if not detected and shutil.which("aplay") and alsa_devices:
            alsa_device = alsa_devices[0]
            detected = ["aplay", "-D", alsa_device]
            dev_name = f"ALSA {alsa_device} (aplay)"

        # 5. 最保守：系统默认
        if not detected:
            if shutil.which("aplay"):
                detected = ["aplay"]
                dev_name = "ALSA 系统默认"
            elif shutil.which("mpv"):
                detected = ["mpv", "--no-video"]
                dev_name = "mpv 系统默认"
            elif shutil.which("paplay"):
                detected = ["paplay"]
                dev_name = "PulseAudio 默认"

        if detected:
            self._play_cmd = detected
            self._detected_device_name = dev_name
            print(f"   音频输出设备: {dev_name} → {' '.join(detected)}")
        else:
            self._play_cmd = None
            print("   ⚠️ 未找到可用的音频播放设备")

    def _check_edge_tts(self) -> bool:
        try:
            result = subprocess.run(
                ["edge-tts", "--version"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def get_intervention_text(self, severity: str) -> str:
        return self.INTERVENTION_TEXTS.get(severity, self.INTERVENTION_TEXTS["low"])

    def speak(self, text: str, severity: str = "low") -> bool:
        if self.is_speaking:
            print("   TTS正在播放，跳过")
            return False

        self.is_speaking = True
        try:
            if self.edge_tts_available:
                return self._speak_with_edge_tts(text)
            else:
                self._speak_simulation(text)
                return False
        finally:
            self.is_speaking = False

    def _speak_with_edge_tts(self, text: str) -> bool:
        import edge_tts
        import asyncio

        output_file = self.output_dir / f"intervention_{int(time.time() * 1000)}.mp3"

        async def generate():
            communicate = edge_tts.Communicate(
                text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume
            )
            await communicate.save(str(output_file))

        try:
            asyncio.run(generate())
            played = self._play_audio(str(output_file))
            try:
                output_file.unlink()
            except:
                pass
            return played
        except Exception as e:
            print(f"Edge TTS生成失败: {e}")
            self._speak_simulation(text)
            return False

    def _play_audio(self, file_path: str) -> bool:
        """
        按优先级尝试播放音频。
        优先用检测到的设备，其次依次尝试各播放器。
        """
        if not self._play_cmd:
            print("   ⚠️ 无可用播放器，跳过")
            return False

        cmd = self._play_cmd
        player = cmd[0]

        # 构造完整命令
        if player == "paplay":
            # paplay 接受 --device 指定 sink。
            args = cmd[1:] + [file_path]
            full_cmd = ["paplay"] + args
        elif player == "mpv":
            args = cmd[1:] + [file_path]
            full_cmd = ["mpv"] + args
        elif player == "aplay":
            args = cmd[1:] + [file_path]
            full_cmd = ["aplay"] + args
        else:
            full_cmd = cmd + [file_path]

        print(f"   播放命令: {' '.join(full_cmd)}")
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                print(f"   ✓ 播放成功 ({self._detected_device_name})")
                return True
            else:
                stderr = result.stderr.strip()
                print(f"   播放失败: {stderr[:100]}")
                # 降级：尝试其他播放器
                return self._play_fallback(file_path)
        except subprocess.TimeoutExpired:
            print("   播放超时")
            return False
        except FileNotFoundError:
            print(f"   播放器 {player} 未找到，降级尝试")
            return self._play_fallback(file_path)
        except Exception as e:
            print(f"   播放异常: {e}")
            return self._play_fallback(file_path)

    def _play_fallback(self, file_path: str) -> bool:
        """降级播放策略：paplay → mpv → aplay（不指定设备）"""
        strategies = [
            # (player, args)
            ("paplay", [file_path]),
            ("mpv", ["--no-video", file_path]),
            ("ffmpeg", ["-i", file_path, "-f", "alsa", "default"]),
            ("aplay", [file_path]),
        ]

        for player, args in strategies:
            if not shutil.which(player):
                continue
            cmd = [player] + args
            print(f"   降级尝试: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    print(f"   ✓ 降级播放成功 ({player})")
                    return True
                else:
                    print(f"   {player} 失败: {result.stderr[:60]}")
            except Exception as e:
                print(f"   {player} 异常: {e}")
        print("   ⚠️ 所有播放方式均失败")
        return False

    def _speak_simulation(self, text: str):
        print(f"\n🔊 [TTS模拟] {text}")
        time.sleep(len(text) * 0.1)

    def speak_async(self, text: str, severity: str = "low"):
        thread = threading.Thread(target=self.speak, args=(text, severity), daemon=True)
        thread.start()

    def set_voice(self, voice: str):
        self.voice = voice

    def set_rate(self, rate: str):
        self.rate = rate

    def set_volume(self, volume: str):
        self.volume = volume

    def test_playback(self) -> bool:
        """测试播放一段正弦波，返回是否成功"""
        import struct, wave, math

        wav_path = self.output_dir / "test_tone.wav"
        with wave.open(str(wav_path), "w") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(8000)
            for i in range(8000 * 2):  # 2秒
                f.writeframes(struct.pack("<h", int(16000 * math.sin(2 * math.pi * 440 * i / 8000))))

        if self._play_cmd:
            played = self._play_audio(str(wav_path))
        else:
            played = self._play_fallback(str(wav_path))

        try:
            wav_path.unlink()
        except:
            pass
        return played

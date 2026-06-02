#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 DashScope TTS 引擎
支持 Sambert / CosyVoice 语音合成
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from tts_engine import detect_alsa_playback_devices


class AliTTSEngine:
    """阿里云 TTS 引擎"""
    
    def __init__(self, api_key: str, model: str = "sambert-zhichu-v1", voice: str = "zhichu"):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.output_device = os.getenv("VD_AUDIO_OUTPUT_DEVICE", "").strip()
        self._initialized = False
        
    def load(self):
        """初始化 TTS 客户端"""
        try:
            import dashscope
            dashscope.api_key = self.api_key
            self._initialized = True
            print(f"   阿里云 TTS 引擎初始化完成 (模型: {self.model})")
        except ImportError:
            raise RuntimeError("请安装 dashscope: pip install dashscope")
    
    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[bytes]:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径（可选）
        
        Returns:
            音频数据 bytes，失败返回 None
        """
        if not self._initialized:
            self.load()
            
        try:
            import dashscope
            
            # 使用旧版 API (更稳定)
            response = dashscope.audio.tts.SpeechSynthesizer.call(
                model=self.model,
                text=text,
                format="wav"
            )
            
            audio = response.get_audio_data()
            
            if audio:
                if output_path:
                    with open(output_path, "wb") as f:
                        f.write(audio)
                return audio
            
            return None
            
        except Exception as e:
            print(f"阿里云 TTS 异常: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def synthesize_stream(self, text: str):
        """
        流式合成（实时播放场景）
        
        Yields:
            音频数据块
        """
        if not self._initialized:
            self.load()
            
        try:
            import dashscope
            
            # 流式 TTS 需要用 WebSocket
            # 暂时用同步方式分块返回
            audio = self.synthesize(text)
            if audio:
                # 分成小块返回
                chunk_size = 4096
                for i in range(0, len(audio), chunk_size):
                    yield audio[i:i+chunk_size]
                    
        except Exception as e:
            print(f"阿里云 TTS 流式合成异常: {e}")

    # === 干预方法 (与 TTSEngine 接口对齐) ===
    
    INTERVENTION_TEXTS = {
        "low": "请注意控制一下情绪，冷静沟通效果更好哦。",
        "medium": "我建议大家先冷静一下，深呼吸，等情绪平复了再继续聊。",
        "high": "请立即停止争吵！情绪激动时说的话容易伤害到彼此，请先冷静几分钟。",
        "critical": "检测到严重冲突！请双方立刻分开冷静，必要时可以寻求帮助。"
    }
    
    is_speaking = False
    
    def get_intervention_text(self, severity: str) -> str:
        """获取干预话术"""
        return self.INTERVENTION_TEXTS.get(severity, self.INTERVENTION_TEXTS["low"])
    
    def _play_wav(self, audio_data: bytes) -> bool:
        """Play cloud-generated WAV audio through the configured USB speaker."""
        with tempfile.NamedTemporaryFile(prefix="intervention_tts_", suffix=".wav", delete=False) as wav_file:
            wav_file.write(audio_data)
            wav_path = Path(wav_file.name)

        devices = []
        if self.output_device:
            devices.append(self.output_device)
        for device in detect_alsa_playback_devices():
            if device not in devices:
                devices.append(device)
        devices.append("default")

        try:
            for device in devices:
                try:
                    result = subprocess.run(
                        ["aplay", "-q", "-D", device, str(wav_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=15
                    )
                    if result.returncode == 0:
                        print(f"   TTS 播放成功 (ALSA {device})")
                        return True
                except Exception:
                    continue
            print("   TTS 合成成功，但音箱播放失败")
            return False
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass

    def speak(self, text: str = None, severity: str = "low") -> bool:
        """生成并播放 TTS 语音"""
        if self.is_speaking:
            print("   TTS 正在播放，跳过")
            return False
        
        if text is None:
            text = self.get_intervention_text(severity)
        
        self.is_speaking = True
        try:
            audio_data = self.synthesize(text)
            if audio_data:
                return self._play_wav(audio_data)
            else:
                print("   TTS 合成失败，跳过播放")
                return False
        except Exception as e:
            print(f"   TTS 播放异常: {e}")
            return False
        finally:
            self.is_speaking = False

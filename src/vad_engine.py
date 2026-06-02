#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VAD (Voice Activity Detection) 人声检测模块
支持句子级别的语音分段
混合策略: Silero VAD + 能量预过滤
"""

import numpy as np
from typing import Optional, List
from scipy.io.wavfile import write
import torch
import time
import os
from pathlib import Path


class VADEngine:
    """VAD人声检测引擎 - 支持句子分段"""
    
    SILERO_CHUNK_SIZE = 512  # 32ms @ 16kHz
    
    def __init__(self, 
                 threshold: float = 0.5, 
                 min_speech_duration: float = 0.5,
                 silence_duration: float = 0.8,
                 max_sentence_duration: float = 10.0,
                 audio_save_dir: str = None):
        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.silence_duration = silence_duration
        self.max_sentence_duration = max_sentence_duration
        self.model = None
        self.sample_rate = 16000
        
        # 能量预过滤阈值 (低于此值直接判无语音)
        self.energy_floor = 300
        
        # 句子缓冲
        self.audio_buffer: List[np.ndarray] = []
        self.buffer_start_time: Optional[float] = None
        default_audio_dir = Path(__file__).resolve().parent.parent / "audio"
        if audio_save_dir is None:
            self.audio_save_dir = os.getenv("VD_AUDIO_DIR", str(default_audio_dir))
        else:
            self.audio_save_dir = audio_save_dir
        self.last_speech_time: Optional[float] = None
        self.is_speaking = False
        
    def load(self):
        """加载VAD模型"""
        try:
            torch.set_num_threads(1)
            result = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                trust_repo=True
            )
            if isinstance(result, tuple):
                self.model = result[0]
            else:
                self.model = result
            print("   Silero VAD模型加载成功")
        except Exception as e:
            print(f"   Silero VAD加载失败，使用能量检测: {e}")
            self.model = None
    
    def detect(self, audio: np.ndarray) -> bool:
        """检测音频中是否包含人声"""
        # 1. 能量预过滤 - 低于阈值直接判无语音
        rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
        if rms < self.energy_floor:
            return False
        
        # 2. Silero VAD
        if self.model is not None:
            return self._detect_with_silero(audio)
        else:
            # 3. 纯能量检测 (fallback)
            return rms > 500
    
    def _detect_with_silero(self, audio: np.ndarray) -> bool:
        """使用Silero VAD检测 - 分块处理"""
        try:
            audio_float = audio.astype(np.float32) / 32768.0
            chunks = []
            for i in range(0, len(audio_float), self.SILERO_CHUNK_SIZE):
                chunk = audio_float[i:i + self.SILERO_CHUNK_SIZE]
                if len(chunk) < self.SILERO_CHUNK_SIZE:
                    chunk = np.pad(chunk, (0, self.SILERO_CHUNK_SIZE - len(chunk)))
                chunks.append(chunk)
            
            if not chunks:
                return False
            
            speech_count = 0
            for chunk in chunks:
                tensor = torch.from_numpy(chunk)
                prob = self.model(tensor, self.sample_rate).item()
                if prob > self.threshold:
                    speech_count += 1
            
            ratio = speech_count / len(chunks)
            return ratio > 0.3
            
        except Exception as e:
            # Silero 出错时回退到能量检测
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
            return rms > 500
    
    def process_audio(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """
        处理音频块，返回完整的句子音频
        
        Returns:
            None: 句子未完成，继续收集
            np.ndarray: 完整句子的音频
        """
        current_time = time.time()
        has_speech = self.detect(audio)
        
        if has_speech:
            if self.buffer_start_time is None:
                self.buffer_start_time = current_time
                print(f"[VAD] 开始收集句子...")
            
            self.audio_buffer.append(audio)
            self.last_speech_time = current_time
            self.is_speaking = True
            
            # 最大长度强制结束
            if self.buffer_start_time and (current_time - self.buffer_start_time) > self.max_sentence_duration:
                print(f"[VAD] 句子过长 ({self.max_sentence_duration}s)，强制结束")
                return self._flush_buffer()
            
            return None
        else:
            # 无语音
            if self.is_speaking:
                self.audio_buffer.append(audio)
                
                # 静音超时 → 句子结束
                if self.last_speech_time and (current_time - self.last_speech_time) > self.silence_duration:
                    print(f"[VAD] 检测到句子结束 (静音 {self.silence_duration}s)")
                    return self._flush_buffer()
            
            return None
    
    def force_flush(self) -> Optional[np.ndarray]:
        """强制获取当前缓冲区"""
        if len(self.audio_buffer) > 0:
            return self._flush_buffer()
        return None
    
    def _flush_buffer(self) -> np.ndarray:
        """合并并清空缓冲区"""
        if not self.audio_buffer:
            return None
        
        # 保存音频到 wav 文件
        if self.audio_save_dir and self.audio_buffer:
            import os, tempfile, datetime
            os.makedirs(self.audio_save_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            wav_path = os.path.join(self.audio_save_dir, f"audio_{timestamp}.wav")
            try:
                all_audio = np.concatenate(self.audio_buffer)
                write(wav_path, self.sample_rate, all_audio)
                print(f"[录音] 已保存: {wav_path} ({len(all_audio)/self.sample_rate:.1f}s)")
            except Exception as e:
                print(f"[录音] 保存失败: {e}")
        result = np.concatenate(self.audio_buffer)
        duration = len(result) / self.sample_rate
        print(f"[VAD] 句子完成: {duration:.1f}s, {len(self.audio_buffer)} chunks")
        
        self.audio_buffer = []
        self.buffer_start_time = None
        self.last_speech_time = None
        self.is_speaking = False
        
        return result

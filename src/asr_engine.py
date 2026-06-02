#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端侧语音转文字模块
使用OpenAI Whisper base模型 (74M参数，无需GPU)
本地离线转写，保护隐私
"""

import re
import whisper
import numpy as np
from typing import Optional
import torch


class ASREngine:
    """Whisper ASR引擎 - 端侧语音转文字"""
    
    def __init__(self, model_size: str = "base"):
        """
        初始化ASR引擎
        
        Args:
            model_size: whisper模型大小 (tiny/base/small/medium/large)
                        树莓派5推荐base (74M)，Mac Mini可用small
        """
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
    def load(self):
        """加载Whisper模型"""
        print(f"   加载Whisper {self.model_size} 模型 (设备: {self.device})...")
        
        try:
            # 优先尝试本地模型
            model_path = None  # 可以指定本地模型路径
            
            if model_path and model_path.exists():
                self.model = whisper.load_model(str(model_path), device=self.device)
            else:
                self.model = whisper.load_model(self.model_size, device=self.device)
            
            print(f"   Whisper模型加载完成")
            
        except Exception as e:
            raise RuntimeError(f"Whisper模型加载失败: {e}")
    
    def _is_hallucination(self, text: str, result: dict) -> bool:
        """
        检测是否是Whisper幻觉输出
        
        检测策略:
        1. 重复模式检测：同一短语重复3次以上
        2. 置信度检测：avg_logprob 过低说明不可靠
        3. 无意义字符检测：标点符号过多
        """
        if not text:
            return True
        
        # 1. 检查重复模式（如"这些东西,这些东西,这些东西,"）
        # 分割后统计各片段出现次数
        parts = re.split(r'[,，、\s]+', text.strip().rstrip(','))
        parts = [p.strip() for p in parts if p.strip()]
        if parts:
            # 统计最常见片段的出现次数
            from collections import Counter
            counts = Counter(parts)
            max_count = counts.most_common(1)[0][1]
            # 如果同一个片段重复超过2次，且总片段数<=5，认为是幻觉
            if max_count >= 3 and len(parts) <= 5:
                return True
            # 如果完全重复且片段数<=3
            if len(parts) == 1 and len(text) > 10:
                return True
        
        # 2. 检查 Whisper 置信度 (avg_logprob)
        segments = result.get("segments", [])
        if segments:
            logprobs = [seg.get("avg_logprob", 0) for seg in segments]
            avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0
            # avg_logprob < -1.0 通常表示不可靠
            if avg_logprob < -1.0:
                return True
        
        # 3. 标点符号过多（>50%是标点）
        alpha_count = sum(1 for c in text if c.isalpha() or c.isdigit())
        if len(text) > 0 and alpha_count / len(text) < 0.3:
            return True
        
        return False
    
    def transcribe(self, audio: np.ndarray) -> Optional[str]:
        """
        将音频转写为文字
        
        Args:
            audio: int16 numpy数组，16kHz采样率
            
        Returns:
            转写文本，失败返回None
        """
        if self.model is None:
            raise RuntimeError("ASR模型未加载")
        
        try:
            # 确保音频格式正确
            if len(audio) < 1600:  # 少于100ms
                return None
            
            # 转换为float32
            audio_float = audio.astype(np.float32) / 32768.0
            
            # 转写参数
            options = {
                "language": "zh",  # 中文
                "task": "transcribe",
                "beam_size": 3,
                "best_of": 3,
                "temperature": 0.0,  # 确定性输出
                "fp16": torch.cuda.is_available(),  # 仅GPU启用
            }
            
            # 执行转写
            result = self.model.transcribe(audio_float, **options)
            
            text = result["text"].strip()
            if not text:
                return None
            
            # 过滤幻觉输出
            if self._is_hallucination(text, result):
                return None
            
            return text
            
        except Exception as e:
            print(f"ASR转写错误: {e}")
            return None
    
    def transcribe_with_timestamps(self, audio: np.ndarray) -> Optional[dict]:
        """转写并返回带时间戳的结果"""
        if self.model is None:
            raise RuntimeError("ASR模型未加载")
        
        try:
            audio_float = audio.astype(np.float32) / 32768.0
            
            options = {
                "language": "zh",
                "task": "transcribe",
                "beam_size": 3,
                "temperature": 0.0,
                "word_timestamps": True,
            }
            
            result = self.model.transcribe(audio_float, **options)
            
            return {
                "text": result["text"].strip(),
                "segments": result.get("segments", []),
                "language": result.get("language", "zh")
            }
            
        except Exception as e:
            print(f"ASR转写错误: {e}")
            return None
    
    def set_model(self, model_size: str):
        """动态切换模型大小"""
        if model_size != self.model_size:
            self.model_size = model_size
            self.model = whisper.load_model(model_size, device=self.device)
            print(f"已切换到 {model_size} 模型")


class FasterWhisperEngine:
    """
    Faster-Whisper引擎 (可选，性能更好)
    使用CTranslate2加速推理，CPU上比Whisper快2-4倍
    """
    
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000
        
    def load(self):
        """加载Faster-Whisper模型"""
        try:
            from faster_whisper import WhisperModel
            
            # CPU推理，int8量化
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )
            print(f"   Faster-Whisper {self.model_size} 模型加载完成 (CPU int8)")
            
        except ImportError:
            print("   faster-whisper未安装，回退到标准Whisper")
            self.model = None
            
    def transcribe(self, audio: np.ndarray) -> Optional[str]:
        """转写音频"""
        if self.model is None:
            return None
            
        try:
            audio_float = audio.astype(np.float32) / 32768.0
            
            segments, info = self.model.transcribe(
                audio_float,
                language="zh",
                beam_size=3,
                vad_filter=True
            )
            
            text = "".join([seg.text for seg in segments])
            return text.strip() if text else None
            
        except Exception as e:
            print(f"Faster-Whisper转写错误: {e}")
            return None

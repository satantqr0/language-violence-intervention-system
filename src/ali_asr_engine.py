#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 ASR 引擎 - 流式识别模式
使用 DashScope SDK (WebSocket) 持续流式识别
paraformer-realtime-v2 设计为实时流式输入，边发边识别

工作模式：
1. start_stream() — 开启一个识别会话
2. send_audio()   — 持续发送音频帧
3. get_result()   — 获取当前识别结果
4. end_stream()   — 结束会话，返回最终结果
"""

import numpy as np
import threading
from typing import Optional
from dashscope.audio.asr import Recognition, RecognitionCallback
import dashscope
import time


class AliASREngine:
    """阿里云 ASR 引擎 — 流式模式"""
    
    # paraformer-realtime-v2 支持的中文方言列表
    ALL_DIALECTS = [
        "zh",      # 普通话（必须包含，作为基准）
        "上海话", "吴语", "闽南语", "东北话",
        "甘肃话", "贵州话", "河南话", "湖北话",
        "湖南话", "江西话", "宁夏话", "山西话",
        "陕西话", "山东话", "四川话", "天津话",
        "云南话", "粤语",
    ]
    
    def __init__(self, api_key: str, model: str = "paraformer-realtime-v2",
                 language_hints: list = None):
        self.api_key = api_key
        self.model = model
        self.sample_rate = 16000
        self.max_audio_seconds = 20
        
        # language_hints 处理
        if language_hints and "auto" in language_hints:
            self.language_hints = self.ALL_DIALECTS
            self._hint_mode = "auto"
        elif language_hints:
            self.language_hints = language_hints
            self._hint_mode = "manual"
        else:
            self.language_hints = self.ALL_DIALECTS
            self._hint_mode = "auto"
        
        # 流式会话状态
        self._recognition = None
        self._final_text = ""
        self._all_sentences = []
        self._is_completed = False
        self._error_msg = None
        self._lock = threading.Lock()
        
    def load(self):
        dashscope.api_key = self.api_key
        if self._hint_mode == "auto":
            print(f"   阿里云 ASR 引擎初始化完成 (模型: {self.model}, 方言: 自动检测)")
        else:
            print(f"   阿里云 ASR 引擎初始化完成 (模型: {self.model}, 方言: {self.language_hints})")
    
    # ========== 流式模式 API ==========
    
    def start_stream(self):
        """开始一个流式识别会话"""
        with self._lock:
            self._final_text = ""
            self._all_sentences = []
            self._is_completed = False
            self._error_msg = None
        
        engine = self  # 闭包引用
        
        class StreamCallback(RecognitionCallback):
            def on_complete(self):
                with engine._lock:
                    engine._is_completed = True
                    
            def on_error(self, result):
                with engine._lock:
                    engine._error_msg = str(result)
                    engine._is_completed = True
                    
            def on_event(self, result):
                s = result.get_sentence()
                if s and s.get("text"):
                    with engine._lock:
                        # 只保留最新结果（paraformer 会不断修正）
                        engine._final_text = s["text"]
        
        recog_params = dict(
            model=self.model,
            format="pcm",
            sample_rate=self.sample_rate,
            callback=StreamCallback()
        )
        # language_hints is only supported by the v2 realtime model.
        if self.language_hints and self.model == "paraformer-realtime-v2":
            recog_params["language_hints"] = self.language_hints
        
        self._recognition = Recognition(**recog_params)
        self._recognition.start()
    
    def send_audio(self, audio: np.ndarray):
        """向当前会话发送音频帧"""
        if self._recognition is None:
            return
        try:
            self._recognition.send_audio_frame(audio.tobytes())
        except Exception as e:
            print(f"[ASR流式发送异常] {e}")
    
    def get_partial_result(self) -> Optional[str]:
        """获取当前中间识别结果（不结束会话）"""
        with self._lock:
            return self._final_text if self._final_text else None
    
    def end_stream(self, timeout: float = 5.0) -> Optional[str]:
        """
        结束流式会话，返回最终识别结果
        
        Args:
            timeout: 等待最终结果的最大秒数
        """
        if self._recognition is None:
            return None
        
        try:
            self._recognition.stop()
        except Exception as e:
            print(f"[ASR流式停止异常] {e}")
        
        # 等待最终结果
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._is_completed or self._error_msg:
                    break
            time.sleep(0.05)
        
        with self._lock:
            result = self._final_text.strip() if self._final_text else None
            error = self._error_msg
        
        self._recognition = None
        
        if error:
            print(f"[ASR流式错误] {error[:100]}")
        
        return result
    
    # ========== 兼容模式：一次性识别（内部仍用流式发送） ==========
    
    def transcribe(self, audio: np.ndarray) -> Optional[str]:
        """
        一次性识别（兼容旧接口）
        内部改为：分块流式发送，模拟实时输入
        """
        try:
            max_samples = self.max_audio_seconds * self.sample_rate
            if len(audio) > max_samples:
                audio = audio[:max_samples]
            
            # 开始流式会话
            self.start_stream()
            
            # 分块发送（200ms 一块，模拟实时输入）
            chunk_size = int(self.sample_rate * 0.2)  # 3200 samples = 200ms
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                if len(chunk) < 160:  # 太短的尾部跳过
                    break
                self.send_audio(chunk)
                time.sleep(0.02)  # 20ms 间隔，模拟实时流
            
            # 等一小段让模型处理
            time.sleep(0.3)
            
            # 结束会话，获取结果
            result = self.end_stream(timeout=8.0)
            return result
            
        except Exception as e:
            print(f"ASR 异常: {e}")
            return None

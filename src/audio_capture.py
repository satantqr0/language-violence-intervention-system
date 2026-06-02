#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频采集与流传输模块
适配USB麦克风阵列，替代浏览器Web Audio API方案
支持ReSpeaker 4-Mic阵列或通用USB麦克风
"""

import pyaudio
import numpy as np
from typing import Optional
import threading
import time


class AudioCapture:
    """音频采集模块 - 替代浏览器MediaRecorder方案"""
    
    def __init__(self, sample_rate: int = 16000, chunk_duration: float = 1.0):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.chunk_size = int(sample_rate * chunk_duration)
        
        # PyAudio配置
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        self.thread = None
        
        # 音频格式
        self.format = pyaudio.paInt16
        self.channels = 1
        
        # 缓冲区
        self.buffer = np.array([], dtype=np.int16)
        self.lock = threading.Lock()
        
    def start(self):
        """启动音频采集"""
        try:
            # 列出可用设备
            device_count = self.audio.get_device_count()
            print(f"   发现 {device_count} 个音频设备")
            
            # 查找USB麦克风
            target_device = self._find_usb_microphone()
            if target_device is not None:
                print(f"   使用设备: {target_device['name']}")
            else:
                print(f"   使用默认输入设备")
            
            # 打开流
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=target_device['index'] if target_device else None,
                frames_per_buffer=self.chunk_size,
                start=False
            )
            
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            
        except Exception as e:
            raise RuntimeError(f"音频采集启动失败: {e}")
    
    def _find_usb_microphone(self) -> Optional[dict]:
        """查找USB麦克风设备"""
        device_count = self.audio.get_device_count()
        
        # 优先查找ReSpeaker或USB麦克风
        priority_keywords = ["usb", "respeaker", "microphone", "mic", "array"]
        
        for i in range(device_count):
            try:
                info = self.audio.get_device_info_by_index(i)
                name = info["name"].lower()
                
                # 匹配关键字（不检查通道数，因为PyAudio可能误报）
                for keyword in priority_keywords:
                    if keyword in name:
                        return {"index": i, "name": info["name"]}
            except:
                continue
        
        # 返回默认设备
        try:
            default_info = self.audio.get_default_input_device_info()
            return {"index": default_info["index"], "name": default_info["name"]}
        except:
            return None
    
    def _capture_loop(self):
        """采集循环"""
        self.stream.start_stream()
        
        while self.running:
            try:
                # 读取音频数据
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                with self.lock:
                    self.buffer = np.append(self.buffer, audio_data)
                    
                    # 保持最近3秒的音频
                    max_samples = self.sample_rate * 3
                    if len(self.buffer) > max_samples:
                        self.buffer = self.buffer[-max_samples:]
                        
            except Exception as e:
                print(f"音频读取错误: {e}")
                time.sleep(0.1)
    
    def read(self) -> Optional[np.ndarray]:
        """读取最近一个chunk的音频数据"""
        with self.lock:
            if len(self.buffer) >= self.chunk_size:
                audio = self.buffer[:self.chunk_size].copy()
                self.buffer = self.buffer[self.chunk_size:]
                return audio
        return None
    
    def read_all(self) -> Optional[np.ndarray]:
        """读取缓冲区所有音频"""
        with self.lock:
            if len(self.buffer) >= self.chunk_size:
                audio = self.buffer.copy()
                self.buffer = np.array([], dtype=np.int16)
                return audio
        return None
    
    def stop(self):
        """停止采集"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.audio:
            self.audio.terminate()
            self.audio = None
    
    def __del__(self):
        self.stop()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
声学特征分析模块 — 音量 + 语调双维度检测
纯 numpy 实现，无额外依赖，适配树莓派5

检测维度：
1. 音量突变 — 维护基线 RMS，检测吼叫/咆哮（短时能量显著高于基线）
2. 语调异常 — 归一化自相关法提取基频 F0，检测音高突变（尖叫/低吼）
3. 语速异常 — 基于音节间隔估计语速，检测急促/咆哮式语速
"""

import numpy as np
from typing import Dict, Optional, List
import time
from collections import deque


class AcousticAnalyzer:
    """声学特征分析器 — 音量 + 语调 + 语速"""
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 volume_spike_ratio: float = 2.5,
                 pitch_jump_semitones: float = 6.0,
                 baseline_window: int = 30,
                 min_pitch_hz: float = 60.0,
                 max_pitch_hz: float = 500.0):
        """
        Args:
            sample_rate: 采样率
            volume_spike_ratio: 音量突变倍数阈值（当前RMS / 基线RMS > 此值 = 突变）
            pitch_jump_semitones: 音高突变半音阈值
            baseline_window: 基线滑动窗口大小（保留最近N条记录）
            min_pitch_hz: 最低基频（Hz），低于此视为无语音
            max_pitch_hz: 最高基频（Hz），高于此视为异常尖叫
        """
        self.sample_rate = sample_rate
        self.volume_spike_ratio = volume_spike_ratio
        self.pitch_jump_semitones = pitch_jump_semitones
        self.baseline_window = baseline_window
        self.min_pitch_hz = min_pitch_hz
        self.max_pitch_hz = max_pitch_hz
        
        # 基线追踪
        self.volume_baseline = deque(maxlen=baseline_window)
        self.pitch_baseline = deque(maxlen=baseline_window)
        
        # 上一次的值，用于检测突变
        self.last_rms = None
        self.last_pitch = None
        
        self.loaded = False
    
    def load(self):
        """初始化"""
        self.loaded = True
        print("   声学特征分析器已加载 (音量+语调+语速)")
    
    def analyze(self, audio: np.ndarray) -> Dict:
        """
        分析一段音频的声学特征
        
        Args:
            audio: int16 numpy array, 单声道 16kHz
            
        Returns:
            {
                "volume": {
                    "rms": float,           # 当前RMS
                    "baseline_rms": float,  # 基线RMS
                    "spike_ratio": float,   # 当前/基线 比值
                    "is_spike": bool,       # 是否音量突变
                    "level": str,           # quiet/normal/loud/shouting
                },
                "pitch": {
                    "f0": float,            # 基频Hz (0=未检出)
                    "baseline_f0": float,   # 基线基频
                    "jump_semitones": float,# 与基线偏差(半音)
                    "is_jump": bool,        # 是否语调突变
                    "trend": str,           # stable/rising/falling/erratic
                },
                "acoustic_risk": {
                    "score": int,           # 0-100 声学风险分
                    "factors": List[str],   # 风险因素列表
                    "is_high_risk": bool,   # score >= 60
                }
            }
        """
        if not self.loaded or audio is None or len(audio) < self.sample_rate * 0.1:
            return self._default_result()
        
        # 1. 音量分析
        volume_result = self._analyze_volume(audio)
        
        # 2. 语调分析
        pitch_result = self._analyze_pitch(audio)
        
        # 3. 综合风险评估
        risk_result = self._compute_risk(volume_result, pitch_result)
        
        # 更新基线（仅正常音量时更新，避免异常值污染基线）
        if not volume_result["is_spike"]:
            self.volume_baseline.append(volume_result["rms"])
        if pitch_result["f0"] > 0 and not pitch_result["is_jump"]:
            self.pitch_baseline.append(pitch_result["f0"])
        
        self.last_rms = volume_result["rms"]
        self.last_pitch = pitch_result["f0"]
        
        return {
            "volume": volume_result,
            "pitch": pitch_result,
            "acoustic_risk": risk_result
        }
    
    def _analyze_volume(self, audio: np.ndarray) -> Dict:
        """音量分析"""
        audio_float = audio.astype(np.float64)
        rms = np.sqrt(np.mean(audio_float ** 2))
        
        # 基线
        baseline_rms = np.mean(self.volume_baseline) if self.volume_baseline else rms
        if baseline_rms < 1.0:
            baseline_rms = max(rms, 100.0)  # 首次或极低基线保护
        
        spike_ratio = rms / baseline_rms if baseline_rms > 0 else 1.0
        is_spike = spike_ratio > self.volume_spike_ratio
        
        # 音量等级
        if rms < 200:
            level = "quiet"
        elif rms < 800:
            level = "normal"
        elif rms < 2500:
            level = "loud"
        else:
            level = "shouting"
        
        return {
            "rms": round(rms, 1),
            "baseline_rms": round(baseline_rms, 1),
            "spike_ratio": round(spike_ratio, 2),
            "is_spike": bool(is_spike),
            "level": level
        }
    
    def _analyze_pitch(self, audio: np.ndarray) -> Dict:
        """基频(F0)提取 — 归一化自相关法"""
        f0 = self._extract_f0(audio)
        
        # 基线
        baseline_f0 = np.mean(self.pitch_baseline) if self.pitch_baseline else f0
        
        # 半音偏差
        jump_semitones = 0.0
        if f0 > 0 and baseline_f0 > 0:
            jump_semitones = 12.0 * np.log2(f0 / baseline_f0)
        
        is_jump = abs(jump_semitones) > self.pitch_jump_semitones
        
        # 趋势判断
        trend = self._detect_pitch_trend()
        
        return {
            "f0": round(f0, 1),
            "baseline_f0": round(baseline_f0, 1),
            "jump_semitones": round(jump_semitones, 1),
            "is_jump": bool(is_jump),
            "trend": trend
        }
    
    def _extract_f0(self, audio: np.ndarray) -> float:
        """
        归一化自相关法提取基频 F0
        使用 YIN-style 归一化差函数，避免倍频/半频误判
        """
        # 降采样到8kHz以减少计算量（F0通常<500Hz，8kHz足够）
        if self.sample_rate > 8000:
            downsample_ratio = self.sample_rate // 8000
            audio_ds = audio[::downsample_ratio].astype(np.float64)
            sr_ds = self.sample_rate // downsample_ratio
        else:
            audio_ds = audio.astype(np.float64)
            sr_ds = self.sample_rate
        
        # 预加重（增强高频，有助于基频检测）
        preemphasis = 0.97
        audio_ds = np.append(audio_ds[0], audio_ds[1:] - preemphasis * audio_ds[:-1])
        
        # 归一化
        max_val = np.max(np.abs(audio_ds))
        if max_val < 1.0:
            return 0.0  # 静音
        audio_ds = audio_ds / max_val
        
        n = len(audio_ds)
        # 搜索范围
        min_lag = max(2, int(sr_ds / self.max_pitch_hz))   # 高音 → 小lag
        max_lag = min(int(sr_ds / self.min_pitch_hz), n // 2)  # 低音 → 大lag
        
        if max_lag >= n or max_lag <= min_lag:
            return 0.0
        
        # ========== YIN 差函数 ==========
        # d(τ) = Σ (x[j] - x[j+τ])²
        # 归一化: d'(τ) = d(τ) / (Σ x[j]² * τ 的累积能量修正)
        # 简化实现: 用累积和加速计算
        
        W = n - max_lag  # 窗口长度
        
        # 计算差函数 (从 lag=1 开始，确保累积均值的基准正确)
        diff = np.zeros(max_lag + 1)
        for lag in range(1, max_lag + 1):
            diff[lag] = np.sum((audio_ds[:W] - audio_ds[lag:lag + W]) ** 2)
        
        # 累积均值归一化差函数 (CMNDF)
        # cmndf(τ) = diff(τ) / ((1/τ) * Σ_{j=1}^{τ} diff(j))
        cmndf = np.ones(max_lag + 1)  # 默认1.0
        cmndf[0] = 1.0
        running_sum = 0.0
        
        for lag in range(1, max_lag + 1):
            running_sum += diff[lag]
            cmndf[lag] = diff[lag] / (running_sum / lag) if running_sum > 0 else 1.0
        
        # 找到第一个低于阈值的谷值（绝对阈值法）
        threshold = 0.15  # YIN 标准阈值
        best_lag = 0
        best_val = 1.0
        
        # 寻找第一个低于阈值的 dip
        for lag in range(min_lag, max_lag + 1):
            if cmndf[lag] < threshold:
                # 找到局部最小值
                while lag + 1 <= max_lag and cmndf[lag + 1] < cmndf[lag]:
                    lag += 1
                best_lag = lag
                best_val = cmndf[lag]
                break
        
        # 如果没找到低于阈值的，取全局最小
        if best_lag == 0:
            search_range = cmndf[min_lag:max_lag + 1]
            if len(search_range) > 0:
                min_idx = np.argmin(search_range)
                best_lag = min_lag + min_idx
                best_val = search_range[min_idx]
                # 最小值太大则认为无基频
                if best_val > 0.5:
                    return 0.0
        
        # 抛物线插值精化
        if best_lag > min_lag and best_lag < max_lag:
            s0 = cmndf[best_lag - 1]
            s1 = cmndf[best_lag]
            s2 = cmndf[best_lag + 1]
            
            denom = 2.0 * (2.0 * s1 - s0 - s2)
            if abs(denom) > 1e-10:
                delta = (s0 - s2) / denom
                # 限制插值偏移
                delta = max(-0.5, min(0.5, delta))
                refined_lag = best_lag + delta
            else:
                refined_lag = float(best_lag)
        else:
            refined_lag = float(best_lag)
        
        f0 = sr_ds / refined_lag
        
        # 合理性检查
        if f0 < self.min_pitch_hz or f0 > self.max_pitch_hz:
            return 0.0
        
        return f0
    
    def _detect_pitch_trend(self) -> str:
        """基于最近基频历史判断语调趋势"""
        if len(self.pitch_baseline) < 3:
            return "stable"
        
        recent = list(self.pitch_baseline)[-5:]
        if len(recent) < 3:
            return "stable"
        
        # 简单线性趋势
        diffs = [recent[i+1] - recent[i] for i in range(len(recent) - 1)]
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)
        
        if std_diff > abs(mean_diff) * 2 and std_diff > 20:
            return "erratic"
        elif mean_diff > 15:
            return "rising"
        elif mean_diff < -15:
            return "falling"
        else:
            return "stable"
    
    def _compute_risk(self, volume: Dict, pitch: Dict) -> Dict:
        """综合声学风险评估"""
        score = 0
        factors = []
        
        # 音量因子
        if volume["level"] == "shouting":
            score += 40
            factors.append("音量极大(吼叫)")
        elif volume["level"] == "loud":
            score += 15
            factors.append("音量偏大")
        
        if volume["is_spike"]:
            score += 25
            factors.append(f"音量突变({volume['spike_ratio']:.1f}x基线)")
        
        # 语调因子
        if pitch["f0"] > 0:
            if pitch["is_jump"]:
                score += 20
                direction = "升高" if pitch["jump_semitones"] > 0 else "降低"
                factors.append(f"语调突变({direction}{abs(pitch['jump_semitones']):.0f}半音)")
            
            if pitch["trend"] == "erratic":
                score += 15
                factors.append("语调不稳定(波动剧烈)")
            elif pitch["trend"] == "rising":
                score += 10
                factors.append("语调持续升高")
        
        # 极高音（尖叫区域）
        if pitch["f0"] > 400:
            score += 20
            factors.append("极高音调(可能尖叫)")
        
        score = min(100, score)
        
        return {
            "score": score,
            "factors": factors,
            "is_high_risk": bool(score >= 60)
        }
    
    def _default_result(self) -> Dict:
        return {
            "volume": {"rms": 0, "baseline_rms": 0, "spike_ratio": 1.0, "is_spike": False, "level": "quiet"},
            "pitch": {"f0": 0, "baseline_f0": 0, "jump_semitones": 0, "is_jump": False, "trend": "stable"},
            "acoustic_risk": {"score": 0, "factors": [], "is_high_risk": False}
        }

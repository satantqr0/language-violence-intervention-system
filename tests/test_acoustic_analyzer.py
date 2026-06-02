#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AcousticAnalyzer 单元测试
测试音量突变、语调检测、声学风险评估
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from acoustic_analyzer import AcousticAnalyzer


def make_sine(freq_hz: float, duration_s: float, sample_rate: int = 16000, amplitude: float = 8000) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.int16)


def make_noise(level_rms: float, duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    samples = int(sample_rate * duration_s)
    raw = np.random.randn(samples) * level_rms
    return raw.astype(np.int16)


class TestBasics:
    def test_init_default(self):
        a = AcousticAnalyzer()
        assert a.sample_rate == 16000
        assert a.volume_spike_ratio == 2.5
        assert a.pitch_jump_semitones == 6.0
        assert not a.loaded

    def test_init_custom(self):
        a = AcousticAnalyzer(volume_spike_ratio=2.0, pitch_jump_semitones=5.0, baseline_window=50)
        assert a.volume_spike_ratio == 2.0
        assert a.pitch_jump_semitones == 5.0
        assert a.baseline_window == 50

    def test_load(self):
        a = AcousticAnalyzer()
        a.load()
        assert a.loaded


class TestVolume:
    def test_quiet_level(self):
        a = AcousticAnalyzer()
        a.load()
        audio = make_noise(50, 1.0)
        result = a.analyze(audio)
        assert result["volume"]["level"] == "quiet"
        assert not result["volume"]["is_spike"]

    def test_shouting_level(self):
        a = AcousticAnalyzer()
        a.load()
        audio = make_noise(3000, 0.5)
        result = a.analyze(audio)
        assert result["volume"]["level"] == "shouting"
        assert result["volume"]["rms"] >= 2500

    def test_volume_spike_detected(self):
        a = AcousticAnalyzer(volume_spike_ratio=2.0)
        a.load()
        normal = make_noise(200, 0.5)
        a.analyze(normal)
        spike = make_noise(600, 0.3)
        result = a.analyze(spike)
        assert result["volume"]["is_spike"]
        assert result["volume"]["spike_ratio"] > 2.0

    def test_volume_spike_not_triggered_on_normal(self):
        a = AcousticAnalyzer(volume_spike_ratio=2.5)
        a.load()
        for _ in range(3):
            audio = make_noise(300, 0.5)
            result = a.analyze(audio)
            assert not result["volume"]["is_spike"]

    def test_baseline_updates(self):
        a = AcousticAnalyzer(baseline_window=5)
        a.load()
        for level in [100, 200, 300]:
            a.analyze(make_noise(level, 0.5))
        assert len(a.volume_baseline) == 3


class TestPitch:
    def test_pitch_detected_from_sine(self):
        a = AcousticAnalyzer(min_pitch_hz=60.0, max_pitch_hz=500.0)
        a.load()
        audio = make_sine(200, 0.5, amplitude=6000)
        result = a.analyze(audio)
        assert result["pitch"]["f0"] > 0
        assert abs(result["pitch"]["f0"] - 200) < 40

    def test_pitch_not_detected_in_silence(self):
        a = AcousticAnalyzer()
        a.load()
        audio = make_noise(5, 0.5)
        result = a.analyze(audio)
        # 静音段不应检出有效基频
        f0 = result["pitch"]["f0"]
        assert f0 == 0 or f0 < 60

    def test_pitch_jump_detected(self):
        a = AcousticAnalyzer(pitch_jump_semitones=6.0)
        a.load()
        audio_low = make_sine(150, 0.5, amplitude=5000)
        a.analyze(audio_low)
        audio_high = make_sine(350, 0.3, amplitude=5000)
        result = a.analyze(audio_high)
        assert result["pitch"]["is_jump"]
        assert result["pitch"]["jump_semitones"] > 6.0


class TestRisk:
    def test_risk_from_shouting(self):
        a = AcousticAnalyzer()
        a.load()
        audio = make_noise(3000, 0.5)
        result = a.analyze(audio)
        # shouting 至少贡献 40 分
        assert result["acoustic_risk"]["score"] >= 40

    def test_risk_from_pitch_jump(self):
        a = AcousticAnalyzer(pitch_jump_semitones=5.0)
        a.load()
        a.analyze(make_sine(120, 0.5, amplitude=5000))
        result = a.analyze(make_sine(360, 0.3, amplitude=5000))
        assert result["acoustic_risk"]["score"] >= 20

    def test_score_capped_at_100(self):
        a = AcousticAnalyzer()
        a.load()
        audio = make_noise(5000, 0.5)
        result = a.analyze(audio)
        assert result["acoustic_risk"]["score"] <= 100

    def test_default_result_short_audio(self):
        a = AcousticAnalyzer()
        a.load()
        result = a.analyze(make_noise(500, 0.05))
        default = a._default_result()
        assert result["acoustic_risk"]["is_high_risk"] == default["acoustic_risk"]["is_high_risk"]


def _run_tests(classes):
    import traceback
    total = passed = failed = 0
    for cls in classes:
        print(f"\n{'='*50}\n  {cls.__name__}\n{'='*50}")
        inst = cls()
        for name in dir(inst):
            if name.startswith("test_"):
                total += 1
                try:
                    getattr(inst, name)()
                    print(f"  PASS  {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  FAIL  {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ERROR {name}: {e}")
                    traceback.print_exc()
                    failed += 1
    print(f"\n{'='*50}\n  结果: {passed}/{total} 通过  {failed}/{total} 失败\n{'='*50}")
    sys.exit(failed)


if __name__ == "__main__":
    _run_tests([TestBasics, TestVolume, TestPitch, TestRisk])


def _run_tests(classes):
    import traceback
    total = passed = failed = 0
    for cls in classes:
        print(f"\n{'='*50}\n  {cls.__name__}\n{'='*50}")
        inst = cls()
        for name in dir(inst):
            if name.startswith("test_"):
                total += 1
                try:
                    getattr(inst, name)()
                    print(f"  PASS  {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  FAIL  {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ERROR {name}: {e}")
                    traceback.print_exc()
                    failed += 1
    print(f"\n{'='*50}\n  结果: {passed}/{total} 通过  {failed}/{total} 失败\n{'='*50}")
    sys.exit(failed)
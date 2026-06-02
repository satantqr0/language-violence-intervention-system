#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Calibrated television and music playback suppression regression tests."""

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from media_guard import MediaGuard, MediaGuardError


def media_audio(amplitude=4200, duration=2.0):
    sample_rate = 16000
    t = np.arange(int(sample_rate * duration)) / sample_rate
    waveform = amplitude * (
        0.70 * np.sin(2 * np.pi * 220 * t) + 0.30 * np.sin(2 * np.pi * 440 * t)
    )
    return waveform.astype(np.int16)


def human_audio(duration=2.0):
    sample_rate = 16000
    t = np.arange(int(sample_rate * duration)) / sample_rate
    envelope = (0.25 + 0.75 * (np.sin(2 * np.pi * 3.2 * t) > 0)).astype(np.float64)
    waveform = envelope * (
        3500 * np.sin(2 * np.pi * (145 + 10 * np.sin(2 * np.pi * 1.2 * t)) * t)
    )
    return waveform.astype(np.int16)


class TestMediaGuard:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = MediaGuard(str(self.tmp), enabled=True, mode="balanced")

    def teardown(self):
        shutil.rmtree(self.tmp)

    def test_calibrated_media_is_suppressed_while_human_sample_passes(self):
        self.engine.calibrate("media", media_audio(), consent=False)
        self.engine.calibrate("human", human_audio(), consent=True)
        media_result = self.engine.classify(media_audio(amplitude=4000))
        human_result = self.engine.classify(human_audio())
        assert media_result["ready"] is True
        assert media_result["suppressed"] is True
        assert media_result["reason"] == "calibrated_media_match"
        assert human_result["suppressed"] is False

    def test_calibration_saves_features_only_and_stats_are_private(self):
        self.engine.calibrate("media", media_audio(), consent=False)
        self.engine.calibrate("human", human_audio(), consent=True)
        decision = self.engine.classify(media_audio())
        self.engine.record_suppression(decision)
        stored = self.engine.templates_file.read_text(encoding="utf-8")
        assert "features" in stored
        assert "audio" not in stored
        assert self.engine.templates_file.stat().st_mode & 0o777 == 0o600
        assert self.engine.stats_file.stat().st_mode & 0o777 == 0o600
        assert self.engine.status()["filtered_count"] == 1

    def test_loud_audio_bypasses_filter_and_human_needs_consent(self):
        self.engine.calibrate("media", media_audio(amplitude=4000), consent=False)
        try:
            self.engine.calibrate("human", human_audio(), consent=False)
            assert False, "human reference samples require consent"
        except MediaGuardError:
            pass
        self.engine.calibrate("human", human_audio(), consent=True)
        loud = self.engine.classify(media_audio(amplitude=12000))
        assert loud["reason"] == "loud_voice_bypass"
        assert loud["suppressed"] is False


def run_tests():
    tests = TestMediaGuard()
    total = passed = failed = 0
    for name in sorted(item for item in dir(tests) if item.startswith("test_")):
        total += 1
        tests.setup()
        try:
            getattr(tests, name)()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")
            failed += 1
        finally:
            tests.teardown()
    print(f"\n{'='*50}\n  结果: {passed}/{total} 通过  {failed}/{total} 失败\n{'='*50}")
    return failed


if __name__ == "__main__":
    raise SystemExit(run_tests())

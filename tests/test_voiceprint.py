#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local voiceprint persistence and decision regression tests."""

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from voiceprint import VoiceprintEngine, VoiceprintError


def fake_extractor(audio):
    return np.array([1.0, 0.0]) if float(np.mean(audio)) > 0 else np.array([0.0, 1.0])


class TestVoiceprintEngine:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.positive = np.full(VoiceprintEngine.SAMPLE_RATE * 3, 1200, dtype=np.int16)
        self.negative = np.full(VoiceprintEngine.SAMPLE_RATE * 3, -1200, dtype=np.int16)

    def teardown(self):
        shutil.rmtree(self.tmp)

    def make_engine(self):
        return VoiceprintEngine(
            data_dir=str(self.tmp),
            model_dir=str(self.tmp / "model"),
            match_threshold=0.45,
            extractor=fake_extractor,
        )

    def test_enrollment_persists_embedding_and_matches_after_reload(self):
        engine = self.make_engine()
        enrolled = engine.enroll("manual-alice", self.positive)
        assert enrolled["enrolled"] is True
        assert enrolled["sample_count"] == 1

        reloaded = self.make_engine()
        match = reloaded.identify_with_score(self.positive)
        assert match["matched"] is True
        assert match["speaker_id"] == "manual-alice"
        assert match["score"] == 1.0
        stored = json.loads((self.tmp / "voiceprints.json").read_text(encoding="utf-8"))
        assert "manual-alice" in stored
        assert "templates" not in reloaded.status()["speakers"][0]

    def test_different_voice_does_not_match_and_template_can_be_deleted(self):
        engine = self.make_engine()
        engine.enroll("manual-alice", self.positive)
        match = engine.identify_with_score(self.negative)
        assert match["speaker_id"] == "unknown"
        assert match["matched"] is False
        assert engine.remove("manual-alice") is True
        assert engine.status()["speaker_count"] == 0

    def test_unknown_profile_and_short_audio_are_rejected(self):
        engine = self.make_engine()
        try:
            engine.enroll("unknown", self.positive)
            assert False, "unknown profile must not be enrolled"
        except VoiceprintError:
            pass

    def test_parallel_status_reads_do_not_corrupt_template_storage(self):
        engine = self.make_engine()
        engine.enroll("manual-alice", self.positive)
        errors = []

        def read_status():
            try:
                for _ in range(20):
                    assert engine.status()["speaker_count"] == 1
                    assert engine.identify_with_score(self.positive)["matched"] is True
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=read_status) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert json.loads((self.tmp / "voiceprints.json").read_text(encoding="utf-8"))
        try:
            engine.enroll("manual-alice", self.positive[:100])
            assert False, "short sample must not be enrolled"
        except VoiceprintError:
            pass


def run_tests():
    tests = TestVoiceprintEngine()
    total = passed = failed = 0
    for name in sorted(n for n in dir(tests) if n.startswith("test_")):
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

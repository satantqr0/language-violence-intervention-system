#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Learning storage privacy regression tests."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from learning_engine import LearningEngine


class TestLearningEnginePrivacy:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown(self):
        shutil.rmtree(self.tmp)

    def test_written_feedback_and_profiles_are_private(self):
        engine = LearningEngine(str(self.tmp))
        engine.add_feedback(
            {"ts": 1, "text": "测试反馈", "speaker": "unknown", "scene": "家庭"},
            "confirmed",
        )
        engine._save_thresholds()
        for path in (
            engine.feedback_file,
            engine.profile_file,
            engine.stats_file,
            engine.thresholds_file,
        ):
            assert path.stat().st_mode & 0o777 == 0o600

    def test_existing_learning_files_are_restricted_when_loaded(self):
        for name in (
            "learning_feedback.jsonl",
            "speaker_profiles.json",
            "learned_thresholds.json",
            "learning_stats.json",
        ):
            path = self.tmp / name
            path.write_text("{}\n", encoding="utf-8")
            os.chmod(path, 0o644)
        engine = LearningEngine(str(self.tmp))
        for path in (
            engine.feedback_file,
            engine.profile_file,
            engine.thresholds_file,
            engine.stats_file,
        ):
            assert path.stat().st_mode & 0o777 == 0o600


def run_tests():
    tests = TestLearningEnginePrivacy()
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

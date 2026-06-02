#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voluntary mental wellbeing screening regression tests."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mental_screening_engine import MentalScreeningEngine, ScreeningError


class TestMentalScreeningEngine:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = MentalScreeningEngine(str(self.tmp))

    def teardown(self):
        shutil.rmtree(self.tmp)

    def test_submission_requires_subject_consent(self):
        try:
            self.engine.submit("member-a", "gad7", [0] * 7, consent=False, self_report=True)
            assert False, "consent is mandatory"
        except ScreeningError:
            pass

    def test_phq9_urgent_self_report_is_scored_without_storing_answers(self):
        result = self.engine.submit(
            "member-a", "phq9", [1, 1, 1, 1, 1, 1, 1, 1, 1],
            consent=True, self_report=True
        )
        assert result["score"] == 9
        assert result["urgent"] is True
        assert result["diagnostic"] is False
        stored = json.loads((self.tmp / "mental_screenings.json").read_text(encoding="utf-8"))
        assert "answers" not in stored["member-a"][0]
        assert (self.tmp / "mental_screenings.json").stat().st_mode & 0o777 == 0o600

    def test_existing_screening_file_is_restricted_when_loaded(self):
        path = self.tmp / "mental_screenings.json"
        path.write_text("{}\n", encoding="utf-8")
        os.chmod(path, 0o644)
        MentalScreeningEngine(str(self.tmp))
        assert path.stat().st_mode & 0o777 == 0o600

    def test_gad7_summary_keeps_latest_score(self):
        self.engine.submit("member-a", "gad7", [1] * 7, consent=True, self_report=True)
        latest = self.engine.submit("member-a", "gad7", [2] * 7, consent=True, self_report=True)
        summary = self.engine.summary("member-a")
        assert latest["score"] == 14
        assert summary["latest"]["gad7"]["score"] == 14
        assert summary["history_count"] == 2
        assert self.engine.clear("member-a") is True
        assert self.engine.summary("member-a")["history_count"] == 0


def run_tests():
    tests = TestMentalScreeningEngine()
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human safety review workflow regression tests."""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from safety_case_engine import SafetyCaseEngine, SafetyCaseError


class TestSafetyCaseEngine:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = SafetyCaseEngine(str(self.tmp))

    def teardown(self):
        shutil.rmtree(self.tmp)

    def test_high_severity_and_safety_language_create_pending_cases(self):
        events = [
            {
                "ts": 1, "timestamp": "2026-05-27 15:00:00", "speaker": "unknown",
                "scene": "家庭", "text": "测试", "is_violence": True,
                "violence_severity": "high",
            },
            {
                "ts": 2, "timestamp": "2026-05-27 15:01:00", "speaker": "member",
                "scene": "家庭", "text": "我不想活了", "is_violence": False,
            },
        ]
        result = self.engine.list_cases(events)
        assert result["summary"]["pending"] == 2
        assert result["summary"]["open"] == 2
        assert any(case["priority"] == "immediate" for case in result["cases"])

    def test_resolution_requires_action_and_note_and_is_private(self):
        event = {
            "ts": 1, "timestamp": "2026-05-27 15:00:00", "speaker": "unknown",
            "scene": "家庭", "text": "测试", "is_violence": True,
            "violence_severity": "high",
        }
        try:
            self.engine.update_case("event:1", [event], {"status": "resolved"}, "console")
            assert False, "resolved cases require documentation"
        except SafetyCaseError:
            pass
        result = self.engine.update_case(
            "event:1",
            [event],
            {"status": "resolved", "action": "contacted_subject", "note": "已核实当前安全。"},
            "console",
        )
        assert result["status"] == "resolved"
        assert result["history"][0]["actor"] == "console"
        assert self.engine.storage_file.stat().st_mode & 0o777 == 0o600

    def test_urgent_self_report_creates_case_without_answers_or_score(self):
        case = self.engine.create_screening_alert("member-a", {
            "urgent": True,
            "submitted_at": "2026-05-27 15:10:00",
            "score": 9,
            "answers": [1] * 9,
        })
        assert case["status"] == "pending"
        content = self.engine.storage_file.read_text(encoding="utf-8")
        assert "answers" not in content
        assert '"score"' not in content


def run_tests():
    tests = TestSafetyCaseEngine()
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

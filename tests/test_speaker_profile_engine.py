#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SpeakerProfileEngine regression tests."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from speaker_profile_engine import SpeakerProfileEngine


class TestSpeakerProfileEngine:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = SpeakerProfileEngine(str(self.tmp / "logs"), str(self.tmp / "data"))

    def teardown(self):
        shutil.rmtree(self.tmp)

    def test_observed_profile_summarizes_risk_without_claiming_identity(self):
        events = [
            {
                "speaker": "unknown", "timestamp": "2026-05-26 19:00:00", "ts": 1,
                "text": "测试", "is_violence": True, "violence_type": "侮辱贬低类",
                "violence_severity": "high", "violence_confidence": 0.92,
                "emotion_type": "愤怒", "emotion_score": 80, "scene": "家庭",
                "intervention_triggered": True, "acoustic_risk_score": 72,
            },
            {
                "speaker": "unknown", "timestamp": "2026-05-26 19:03:00", "ts": 2,
                "text": "测试二", "is_violence": False, "emotion_type": "平静",
                "emotion_score": 20, "scene": "家庭", "intervention_triggered": False,
                "acoustic_risk_score": 10,
            },
        ]
        profile = self.engine.build_profile("unknown", events)
        assert profile["display_name"] == "未识别说话人"
        assert profile["event_count"] == 2
        assert profile["violence_count"] == 1
        assert profile["violence_rate"] == 50.0
        assert profile["intervention_count"] == 1
        assert profile["acoustic_alert_count"] == 1
        assert profile["top_emotion"]["name"] == "愤怒"
        assert profile["content_observation"]["level"] == "high"
        assert len(profile["content_observation"]["dimensions"]) == 5

    def test_manual_record_persists_annotations_as_unbound(self):
        speaker_id = self.engine.create_profile({
            "display_name": "成员 A",
            "relationship": "监护人",
            "attention_level": "watch",
            "notes": "需持续观察",
        })
        reloaded = SpeakerProfileEngine(str(self.tmp / "logs"), str(self.tmp / "data"))
        profile = reloaded.build_profile(speaker_id, [])
        assert profile["source"] == "manual"
        assert profile["display_name"] == "成员 A"
        assert profile["relationship"] == "监护人"
        assert profile["attention_level"] == "watch"
        assert profile["content_observation"]["level"] == "insufficient"
        assert (self.tmp / "data" / "speaker_registry.json").stat().st_mode & 0o777 == 0o600

    def test_voiceprint_templates_are_not_part_of_content_portrait(self):
        speaker_id = self.engine.create_profile({"display_name": "成员 B"})
        (self.tmp / "data" / "voiceprints.json").write_text(
            json.dumps({
                speaker_id: {
                    "templates": [[1.0, 0.0]],
                    "updated_at": "2026-05-27 11:00:00",
                }
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        profile = self.engine.build_profile(speaker_id, [{
            "speaker": speaker_id,
            "timestamp": "2026-05-27 11:01:00",
            "speaker_verified": True,
            "is_violence": False,
        }])
        assert "voiceprint_enrolled" not in profile
        assert "identity_status" not in profile
        assert profile["content_observation"]["level"] == "normal"

    def test_content_observation_flags_distress_and_safety_language(self):
        profile = self.engine.build_profile("member-a", [
            {
                "speaker": "member-a", "timestamp": "2026-05-27 12:01:00",
                "text": "我真的撑不住了，甚至不想活了", "is_violence": False,
            },
            {
                "speaker": "member-a", "timestamp": "2026-05-27 12:02:00",
                "text": "对不起，我们一起解决", "is_violence": False,
            },
        ])
        observation = profile["content_observation"]
        assert observation["requires_immediate_review"] is True
        assert observation["level"] == "high"
        assert any(item["signal"] == "生命安全相关表达" for item in observation["evidence"])


def run_tests():
    tests = TestSpeakerProfileEngine()
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

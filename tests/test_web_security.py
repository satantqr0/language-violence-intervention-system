#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web console authentication and secret-storage regression tests."""

import base64
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web_app


def auth_header(username="console", password="secret-pass"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class TestWebSecurity:
    def setup(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.original_config = web_app.CONFIG_FILE
        self.original_env_file = web_app.ENV_FILE
        self.original_events = web_app.EVENTS_FILE
        self.original_logs_dir = web_app.LOGS_DIR
        self.original_log_dir = web_app.LOG_DIR
        self.original_data_dir = web_app.DATA_DIR
        self.original_voiceprint_cache = web_app._voiceprint_engine_cache
        self.original_voiceprint_key = web_app._voiceprint_engine_key
        self.original_capture_voiceprint_audio = web_app.capture_voiceprint_audio
        self.original_is_main_running = web_app.is_main_running
        self.original_control_detector_service = web_app.control_detector_service
        self.original_env = {
            key: os.environ.get(key)
            for key in ("VD_WEB_USERNAME", "VD_WEB_PASSWORD", "DASHSCOPE_API_KEY", "VD_DATA_DIR")
        }
        web_app.CONFIG_FILE = self.tmp / "config.json"
        web_app.ENV_FILE = self.tmp / ".env"
        web_app.EVENTS_FILE = self.tmp / "events.jsonl"
        web_app.LOGS_DIR = self.tmp
        web_app.LOG_DIR = self.tmp
        web_app.DATA_DIR = self.tmp / "data"
        web_app._voiceprint_engine_cache = None
        web_app._voiceprint_engine_key = None
        web_app.CONFIG_FILE.write_text(
            json.dumps({
                "asr": {"engine": "ali_asr", "model_size": "base"},
                "tts": {"engine": "sambert"},
                "scene": {"default": "家庭", "sensitivity": 0.6},
                "audio": {"save_recordings": False},
                "api": {
                    "dashscope_api_key": "",
                    "semantic_llm": {"api_key": ""},
                    "emotion_llm": {"api_key": ""},
                },
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        os.environ["VD_WEB_USERNAME"] = "console"
        os.environ["VD_WEB_PASSWORD"] = "secret-pass"
        os.environ.pop("DASHSCOPE_API_KEY", None)
        os.environ.pop("VD_DATA_DIR", None)
        self.client = web_app.app.test_client()

    def teardown(self):
        web_app.CONFIG_FILE = self.original_config
        web_app.ENV_FILE = self.original_env_file
        web_app.EVENTS_FILE = self.original_events
        web_app.LOGS_DIR = self.original_logs_dir
        web_app.LOG_DIR = self.original_log_dir
        web_app.DATA_DIR = self.original_data_dir
        web_app._voiceprint_engine_cache = self.original_voiceprint_cache
        web_app._voiceprint_engine_key = self.original_voiceprint_key
        web_app.capture_voiceprint_audio = self.original_capture_voiceprint_audio
        web_app.is_main_running = self.original_is_main_running
        web_app.control_detector_service = self.original_control_detector_service
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp)

    def test_console_requires_credentials(self):
        response = self.client.get("/api/status")
        assert response.status_code == 401
        assert "Basic" in response.headers.get("WWW-Authenticate", "")

    def test_missing_server_credentials_fails_closed(self):
        os.environ.pop("VD_WEB_PASSWORD")
        response = self.client.get("/api/status", headers=auth_header())
        assert response.status_code == 503

    def test_effective_mode_reports_local_fallback_without_key(self):
        response = self.client.get("/api/status", headers=auth_header())
        assert response.status_code == 200
        cfg = response.get_json()["config"]
        assert cfg["effective_asr_engine"] == "local_whisper"
        assert cfg["effective_tts_engine"] == "edge_tts"

    def test_mutation_requires_console_request_header(self):
        response = self.client.post(
            "/api/config",
            headers=auth_header(),
            json={"scene": "儿童保护"},
        )
        assert response.status_code == 403

    def test_api_key_is_written_only_to_env(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        response = self.client.post(
            "/api/config/key",
            headers=headers,
            json={"api_key": "temporary-test-key", "region": "beijing"},
        )
        assert response.status_code == 200
        assert "DASHSCOPE_API_KEY=temporary-test-key" in web_app.ENV_FILE.read_text(encoding="utf-8")
        stored = json.loads(web_app.CONFIG_FILE.read_text(encoding="utf-8"))
        assert stored["api"]["dashscope_api_key"] == ""
        assert stored["api"]["semantic_llm"]["api_key"] == ""

    def test_asr_uses_saved_key_marker_and_returns_runtime_models(self):
        os.environ["DASHSCOPE_API_KEY"] = "stored-dashscope-key"
        original_urlopen = web_app.urllib.request.urlopen
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"data": []}'

        def fake_urlopen(req, **_kwargs):
            captured["authorization"] = req.get_header("Authorization")
            return FakeResponse()

        web_app.urllib.request.urlopen = fake_urlopen
        try:
            response = self.client.post(
                "/api/asr/test",
                headers={**auth_header(), "X-Requested-With": "FamilyViolenceConsole"},
                json={"api_key": "___use_cached___"},
            )
        finally:
            web_app.urllib.request.urlopen = original_urlopen

        assert response.status_code == 200
        assert captured["authorization"] == "Bearer stored-dashscope-key"
        assert response.get_json()["asr_models"][0] == "paraformer-realtime-v2"

    def test_tts_preview_synthesizes_submitted_text(self):
        import ali_tts_engine

        os.environ["DASHSCOPE_API_KEY"] = "stored-dashscope-key"
        captured = {}
        original_load = ali_tts_engine.AliTTSEngine.load
        original_speak = ali_tts_engine.AliTTSEngine.speak

        def fake_load(engine):
            captured["key"] = engine.api_key
            captured["model"] = engine.model

        def fake_speak(_engine, text, severity="low"):
            captured["text"] = text
            return True

        ali_tts_engine.AliTTSEngine.load = fake_load
        ali_tts_engine.AliTTSEngine.speak = fake_speak
        try:
            response = self.client.post(
                "/api/tts/test/playback",
                headers={**auth_header(), "X-Requested-With": "FamilyViolenceConsole"},
                json={
                    "api_key": "___use_cached___",
                    "engine": "sambert",
                    "model": "sambert-zhiyue-v1",
                    "text": "这是实际语音试听。",
                },
            )
        finally:
            ali_tts_engine.AliTTSEngine.load = original_load
            ali_tts_engine.AliTTSEngine.speak = original_speak

        assert response.status_code == 200
        assert captured == {
            "key": "stored-dashscope-key",
            "model": "sambert-zhiyue-v1",
            "text": "这是实际语音试听。",
        }

    def test_speaker_profile_can_be_observed_and_annotated(self):
        event = {
            "speaker": "unknown", "timestamp": "2026-05-26 21:00:00", "ts": 1,
            "text": "测试事件", "is_violence": True, "violence_type": "侮辱贬低类",
            "violence_severity": "medium", "intervention_triggered": True,
            "acoustic_risk_score": 65,
        }
        web_app.EVENTS_FILE.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        response = self.client.get("/api/speakers/unknown/profile", headers=auth_header())
        assert response.status_code == 200
        assert response.get_json()["profile"]["content_observation"]["level"] == "high"
        blocked_screening = self.client.post(
            "/api/speakers/unknown/screenings",
            headers={**auth_header(), "X-Requested-With": "FamilyViolenceConsole"},
            json={"instrument": "gad7", "answers": [0] * 7, "consent": True, "self_report": True},
        )
        assert blocked_screening.status_code == 400
        response = self.client.patch(
            "/api/speakers/unknown",
            headers={**auth_header(), "X-Requested-With": "FamilyViolenceConsole"},
            json={"display_name": "待核验成员", "attention_level": "watch", "relationship": "家庭成员"},
        )
        assert response.status_code == 200
        assert response.get_json()["profile"]["display_name"] == "待核验成员"

    def test_event_export_localizes_internal_display_values(self):
        event = {
            "timestamp": "2026-05-26 21:00:00",
            "text": "测试事件",
            "emotion_type": "烦躁",
            "emotion_intensity": "medium",
            "violence_severity": "high",
            "is_violence": True,
            "speaker": "unknown",
            "speaker_verified": False,
            "scene": "夫妻",
            "intervention_triggered": True,
            "volume_level": "shouting",
            "volume_spike": True,
            "pitch_trend": "falling",
        }
        web_app.EVENTS_FILE.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        response = self.client.get("/api/events/export", headers=auth_header())
        assert response.status_code == 200
        csv_data = response.get_json()["csv_data"]
        for label in ("中", "高风险", "喊叫", "未识别说话人", "降低", "是", "否"):
            assert label in csv_data
        for raw_value in ("medium", "shouting", "unknown", "falling"):
            assert raw_value not in csv_data

    def test_event_marks_are_private(self):
        response = self.client.post(
            "/api/events/mark",
            headers={**auth_header(), "X-Requested-With": "FamilyViolenceConsole"},
            json={"ts": 1234, "mark": "confirmed"},
        )
        assert response.status_code == 200
        assert (self.tmp / "event_marks.json").stat().st_mode & 0o777 == 0o600

    def test_high_risk_event_requires_documented_safety_review(self):
        event = {
            "timestamp": "2026-05-27 16:00:00", "ts": 77,
            "text": "高风险测试", "speaker": "unknown", "scene": "家庭",
            "is_violence": True, "violence_severity": "high",
        }
        web_app.EVENTS_FILE.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        cases = self.client.get("/api/safety/cases", headers=auth_header()).get_json()
        assert cases["summary"]["pending"] == 1
        assert cases["cases"][0]["id"] == "event:77"
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        invalid = self.client.patch(
            "/api/safety/cases/event:77", headers=headers,
            json={"status": "resolved", "action": "contacted_subject", "note": ""},
        )
        assert invalid.status_code == 400
        saved = self.client.patch(
            "/api/safety/cases/event:77", headers=headers,
            json={"status": "resolved", "action": "contacted_subject", "note": "已人工确认当前安全。"},
        )
        assert saved.status_code == 200
        assert saved.get_json()["case"]["status"] == "resolved"
        assert (web_app.DATA_DIR / "safety_cases.json").stat().st_mode & 0o777 == 0o600

    def test_speaker_profile_reads_events_before_large_log_tail(self):
        early = {
            "speaker": "early-member", "timestamp": "2026-05-01 08:00:00", "ts": 1,
            "text": "较早记录", "is_violence": False,
        }
        large_tail = {
            "speaker": "unknown", "timestamp": "2026-05-26 22:00:00", "ts": 2,
            "text": "x" * (600 * 1024), "is_violence": False,
        }
        web_app.EVENTS_FILE.write_text(
            json.dumps(early, ensure_ascii=False) + "\n" + json.dumps(large_tail, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        response = self.client.get("/api/speakers/early-member/profile", headers=auth_header())
        assert response.status_code == 200
        assert response.get_json()["profile"]["event_count"] == 1

    def test_status_reads_requested_count_from_large_event_tail(self):
        events = [
            json.dumps({
                "speaker": "unknown",
                "timestamp": f"2026-05-26 22:{index % 60:02d}:00",
                "ts": index,
                "text": "x" * 700,
                "is_violence": index >= 1190,
            }, ensure_ascii=False)
            for index in range(1200)
        ]
        web_app.EVENTS_FILE.write_text("\n".join(events) + "\n", encoding="utf-8")
        response = self.client.get("/api/status", headers=auth_header())
        assert response.status_code == 200
        stats = response.get_json()["stats"]
        assert stats["total"] == 1000
        assert stats["violence"] == 10

    def test_voiceprint_enroll_test_and_delete_workflow(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        response = self.client.post(
            "/api/speakers",
            headers=headers,
            json={"display_name": "成员 B", "relationship": "家庭成员"},
        )
        assert response.status_code == 201
        speaker_id = response.get_json()["profile"]["speaker_id"]
        fake_engine = web_app.VoiceprintEngine(
            data_dir=str(web_app.DATA_DIR),
            model_dir=str(web_app.DATA_DIR / "model"),
            extractor=lambda _audio: web_app.np.array([1.0, 0.0]),
        )
        web_app._voiceprint_engine_cache = fake_engine
        web_app._voiceprint_engine_key = (str(web_app.DATA_DIR), 0.45, 8, 3)
        def fake_capture(_duration, process_audio=None):
            audio = web_app.np.full(48000, 1000, dtype=web_app.np.int16)
            return process_audio(audio) if process_audio else audio
        web_app.capture_voiceprint_audio = fake_capture

        rejected = self.client.post(
            f"/api/voiceprints/{speaker_id}/enroll", headers=headers, json={"consent": False}
        )
        assert rejected.status_code == 400

        enrolled = self.client.post(
            f"/api/voiceprints/{speaker_id}/enroll", headers=headers, json={"consent": True}
        )
        assert enrolled.status_code == 200
        assert enrolled.get_json()["voiceprint"]["enrolled"] is True
        separated = self.client.get(
            f"/api/speakers/{speaker_id}/profile", headers=auth_header()
        ).get_json()["profile"]
        assert "voiceprint_enrolled" not in separated

        tested = self.client.post(
            f"/api/voiceprints/{speaker_id}/test", headers=headers, json={"consent": True}
        )
        assert tested.status_code == 200
        assert tested.get_json()["match"]["matches_profile"] is True

        status = self.client.get("/api/voiceprints", headers=auth_header()).get_json()
        assert status["speaker_count"] == 1
        selected = self.client.get(
            f"/api/voiceprints/{speaker_id}", headers=auth_header()
        ).get_json()
        assert selected["voiceprint"]["enrolled"] is True
        restarted = []
        web_app.is_main_running = lambda: True
        web_app.control_detector_service = lambda action: restarted.append(action)
        removed = self.client.delete(f"/api/voiceprints/{speaker_id}", headers=headers)
        assert removed.status_code == 200
        assert removed.get_json()["voiceprint"]["enrolled"] is False
        assert restarted == ["restart"]

    def test_self_report_screening_requires_consent_and_is_returned_in_profile(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        response = self.client.post(
            "/api/speakers", headers=headers, json={"display_name": "成员 D"}
        )
        speaker_id = response.get_json()["profile"]["speaker_id"]
        instruments = self.client.get("/api/screenings/instruments", headers=auth_header())
        assert instruments.status_code == 200
        assert {item["id"] for item in instruments.get_json()["instruments"]} == {"phq9", "gad7"}
        blocked = self.client.post(
            f"/api/speakers/{speaker_id}/screenings",
            headers=headers,
            json={"instrument": "gad7", "answers": [1] * 7, "consent": False, "self_report": True},
        )
        assert blocked.status_code == 400
        submitted = self.client.post(
            f"/api/speakers/{speaker_id}/screenings",
            headers=headers,
            json={"instrument": "gad7", "answers": [2] * 7, "consent": True, "self_report": True},
        )
        assert submitted.status_code == 200
        profile = submitted.get_json()["profile"]
        assert profile["screenings"]["latest"]["gad7"]["score"] == 14
        assert profile["screenings"]["latest"]["gad7"]["diagnostic"] is False
        removed = self.client.delete(f"/api/speakers/{speaker_id}/screenings", headers=headers)
        assert removed.status_code == 200
        assert removed.get_json()["profile"]["screenings"]["history_count"] == 0

    def test_urgent_self_report_enters_safety_review_without_item_answers(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        response = self.client.post("/api/speakers", headers=headers, json={"display_name": "成员 E"})
        speaker_id = response.get_json()["profile"]["speaker_id"]
        result = self.client.post(
            f"/api/speakers/{speaker_id}/screenings", headers=headers,
            json={"instrument": "phq9", "answers": [0] * 8 + [1], "consent": True, "self_report": True},
        )
        assert result.status_code == 200
        assert result.get_json()["safety_case"]["status"] == "pending"
        stored = (web_app.DATA_DIR / "safety_cases.json").read_text(encoding="utf-8")
        assert "answers" not in stored
        assert '"score"' not in stored

    def test_media_guard_calibration_requires_consent_and_saves_local_features(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        original_capture = web_app.capture_voiceprint_audio
        sample_media = web_app.np.tile(web_app.np.array([1000, -1000], dtype=web_app.np.int16), 16000)
        sample_human = web_app.np.random.default_rng(1).integers(-2000, 2000, 32000, dtype=web_app.np.int16)
        try:
            web_app.capture_voiceprint_audio = lambda _duration, process_audio=None: (
                process_audio(sample_media) if process_audio else sample_media
            )
            media = self.client.post(
                "/api/media-guard/calibrate/media", headers=headers,
                json={"confirm_source": True},
            )
            assert media.status_code == 200
            rejected = self.client.post(
                "/api/media-guard/calibrate/human", headers=headers,
                json={"confirm_source": True, "consent": False},
            )
            assert rejected.status_code == 400
            web_app.capture_voiceprint_audio = lambda _duration, process_audio=None: (
                process_audio(sample_human) if process_audio else sample_human
            )
            human = self.client.post(
                "/api/media-guard/calibrate/human", headers=headers,
                json={"confirm_source": True, "consent": True},
            )
            assert human.status_code == 200
        finally:
            web_app.capture_voiceprint_audio = original_capture
        status = self.client.get("/api/media-guard", headers=auth_header()).get_json()
        assert status["ready"] is True
        assert status["storage"] == "local_features_only"
        stored = (web_app.DATA_DIR / "media_guard_templates.json").read_text(encoding="utf-8")
        assert "features" in stored
        assert "audio" not in stored
        assert (web_app.DATA_DIR / "media_guard_templates.json").stat().st_mode & 0o777 == 0o600

    def test_media_guard_config_is_exposed_in_status(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        updated = self.client.post(
            "/api/media-guard/config", headers=headers,
            json={"enabled": True, "mode": "strict"},
        )
        assert updated.status_code == 200
        status = self.client.get("/api/status", headers=auth_header()).get_json()
        assert status["config"]["media_guard"]["mode"] == "strict"

    def test_voiceprint_processes_template_before_restarting_detector(self):
        order = []
        original_audio_capture_module = sys.modules.get("audio_capture")

        class FakeCapture:
            def __init__(self, **_kwargs):
                pass

            def start(self):
                order.append("capture")

            def read(self):
                return None

            def read_all(self):
                return web_app.np.full(48000, 1000, dtype=web_app.np.int16)

            def stop(self):
                order.append("stopped")

        sys.modules["audio_capture"] = types.SimpleNamespace(AudioCapture=FakeCapture)
        web_app.is_main_running = lambda: True
        web_app.control_detector_service = lambda action: order.append(action)
        try:
            result = web_app.capture_voiceprint_audio(
                0, lambda _audio: order.append("template_saved") or "ok"
            )
        finally:
            if original_audio_capture_module is None:
                sys.modules.pop("audio_capture", None)
            else:
                sys.modules["audio_capture"] = original_audio_capture_module
        assert result == "ok"
        assert order == ["stop", "capture", "stopped", "template_saved", "start"]

    def test_voiceprint_delete_waits_for_active_capture(self):
        headers = {**auth_header(), "X-Requested-With": "FamilyViolenceConsole"}
        response = self.client.post(
            "/api/speakers", headers=headers, json={"display_name": "成员 C"}
        )
        speaker_id = response.get_json()["profile"]["speaker_id"]
        assert web_app._voiceprint_capture_lock.acquire(blocking=False)
        try:
            blocked = self.client.delete(f"/api/voiceprints/{speaker_id}", headers=headers)
        finally:
            web_app._voiceprint_capture_lock.release()
        assert blocked.status_code == 409
        assert "正在进行" in blocked.get_json()["error"]

    def test_event_stream_finishes_immediately_for_worker_capacity(self):
        response = self.client.get("/api/events/stream", headers=auth_header())
        assert response.status_code == 200
        assert b"retry:" in response.data


def run_tests():
    total = passed = failed = 0
    tests = TestWebSecurity()
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

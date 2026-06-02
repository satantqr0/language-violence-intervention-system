#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EventLogger 单元测试
"""

import sys, os, json, time, tempfile, shutil, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
from event_logger import EventLogger


def make_event(**overrides):
    base = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
        "text": "测试语音",
        "emotion_type": "愤怒",
        "emotion_intensity": "high",
        "emotion_score": 80,
        "violence_type": "侮辱贬低类",
        "violence_confidence": 0.85,
        "violence_severity": "high",
        "is_violence": True,
        "speaker": "user1",
        "scene": "家庭",
        "intervention_triggered": True,
        "intervention_text": "请冷静一下",
        "intervention_threshold": 0.7,
        "volume_level": "loud",
        "volume_rms": 1500,
        "volume_spike": True,
        "volume_spike_ratio": 2.8,
        "pitch_f0": 250,
        "pitch_trend": "rising",
        "pitch_jump": True,
        "acoustic_risk_score": 65,
        "acoustic_risk_factors": ["音量偏大"],
        "analysis_reason": "规则匹配"
    }
    base.update(overrides)
    return base


def mktmp():
    return tempfile.mkdtemp()


class TestBasic:
    def test_init_creates_csv(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        csv_path = Path(tmp) / "events.csv"
        assert csv_path.exists()
        with open(csv_path, encoding="utf-8") as f:
            assert "timestamp" in f.readline()
        logger.close()
        shutil.rmtree(tmp)

    def test_init_creates_jsonl(self):
        # JSONL 文件在首次 log() 后才创建，init 只创建目录
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        jsonl_path = Path(tmp) / "events.jsonl"
        # init 不创建文件，log 后才创建
        assert not jsonl_path.exists()
        logger.log(make_event())
        assert jsonl_path.exists()
        logger.close()
        shutil.rmtree(tmp)

    def test_log_writes_jsonl(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event(text="语音"))
        jsonl_path = Path(tmp) / "events.jsonl"
        with open(jsonl_path, encoding="utf-8") as f:
            data = json.loads(f.readline())
        assert data["text"] == "语音"
        logger.close()
        shutil.rmtree(tmp)

    def test_log_writes_csv(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event())
        csv_path = Path(tmp) / "events.csv"
        with open(csv_path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1
        assert "测试语音" in lines[1]
        logger.close()
        shutil.rmtree(tmp)

    def test_event_log_files_are_private(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event())
        assert (Path(tmp) / "events.csv").stat().st_mode & 0o777 == 0o600
        assert (Path(tmp) / "events.jsonl").stat().st_mode & 0o777 == 0o600
        logger.close()
        shutil.rmtree(tmp)


class TestQuery:
    def test_get_recent_events(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        for i in range(5):
            logger.log(make_event(**{"text": f"语音{i}"}))
        events = logger.get_recent_events(limit=3)
        # 最近 3 条按插入顺序返回
        assert len(events) == 3
        # 最后写入的是语音4
        assert events[2]["text"] == "语音4", f"期望语音4，实际{events[2]['text']}"
        logger.close()
        shutil.rmtree(tmp)

    def test_get_recent_empty(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        events = logger.get_recent_events(limit=10)
        assert events == []
        logger.close()
        shutil.rmtree(tmp)

    def test_get_violence_events(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event(is_violence=True))
        logger.log(make_event(is_violence=False))
        logger.log(make_event(is_violence=True))
        violence = logger.get_violence_events(limit=10)
        assert len(violence) == 2
        assert all(e["is_violence"] for e in violence)
        logger.close()
        shutil.rmtree(tmp)

    def test_get_events_by_scene(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event(scene="家庭"))
        logger.log(make_event(scene="夫妻"))
        logger.log(make_event(scene="家庭"))
        home = logger.get_events_by_scene("家庭", limit=10)
        assert len(home) == 2
        assert all(e["scene"] == "家庭" for e in home)
        logger.close()
        shutil.rmtree(tmp)


class TestExport:
    def test_export_to_csv(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        for i in range(3):
            logger.log(make_event(**{"text": f"语音{i}"}))
        out = os.path.join(tmp, "exported.csv")
        logger.export_to_csv(out)
        with open(out, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 4  # header + 3
        assert Path(out).stat().st_mode & 0o777 == 0o600
        logger.close()
        shutil.rmtree(tmp)

    def test_export_date_filter(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event(timestamp="2026-01-01 10:00:00"))
        logger.log(make_event(timestamp="2026-05-26 10:00:00"))
        out = os.path.join(tmp, "filtered.csv")
        logger.export_to_csv(out, start_date="2026-05-01", end_date="2026-05-31")
        with open(out, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1
        logger.close()
        shutil.rmtree(tmp)

    def test_export_empty(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        out = os.path.join(tmp, "empty.csv")
        logger.export_to_csv(out)
        with open(out, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1  # only header
        logger.close()
        shutil.rmtree(tmp)


class TestStats:
    def test_get_statistics(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event(is_violence=True))
        logger.log(make_event(is_violence=False))
        logger.log(make_event(is_violence=True))
        stats = logger.get_statistics()
        assert stats["total_events"] == 3
        assert stats["violence_count"] == 2
        logger.close()
        shutil.rmtree(tmp)

    def test_get_statistics_empty(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        stats = logger.get_statistics()
        assert stats["total_events"] == 0
        assert stats["violence_count"] == 0
        logger.close()
        shutil.rmtree(tmp)


class TestConcurrent:
    def test_concurrent_log(self):
        tmp = mktmp()
        logger = EventLogger(log_dir=tmp)
        errors = []
        def write_batch(start):
            try:
                for i in range(50):
                    logger.log(make_event(**{"text": f"event_{start}_{i}"}))
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=write_batch, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        logger.close()
        jsonl_path = Path(tmp) / "events.jsonl"
        with open(jsonl_path, encoding="utf-8") as f:
            lines = f.readlines()
        shutil.rmtree(tmp)
        assert len(errors) == 0, f"并发错误: {errors}"
        assert len(lines) == 200


class TestCsvMigration:
    def test_csv_header_mismatch_backs_up(self):
        tmp = mktmp()
        old_csv = Path(tmp) / "events.csv"
        old_csv.write_text("timestamp,text\n2026-01-01,hello\n", encoding="utf-8")
        logger = EventLogger(log_dir=tmp)
        logger.log(make_event())
        backups = list(Path(tmp).glob("events.legacy_*.csv"))
        assert len(backups) == 1
        assert backups[0].stat().st_mode & 0o777 == 0o600
        with open(old_csv, encoding="utf-8") as f:
            header = f.readline()
        assert "acoustic_risk_score" in header
        logger.close()
        shutil.rmtree(tmp)


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
    _run_tests([TestBasic, TestQuery, TestExport, TestStats, TestConcurrent, TestCsvMigration])

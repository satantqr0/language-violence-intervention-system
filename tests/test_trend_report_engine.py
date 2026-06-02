#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendReportEngine 单元测试
"""

import sys, os, json, time, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
from trend_report_engine import TrendReportEngine


def make_event(**overrides):
    base = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
        "text": "测试语音",
        "is_violence": False,
        "violence_type": None,
        "violence_confidence": 0.0,
        "violence_severity": "low",
        "scene": "家庭",
        "speaker": "user1",
        "intervention_triggered": False,
        "acoustic_risk_score": 0,
        "volume_spike": False,
        "emotion_type": "平静",
    }
    base.update(overrides)
    return base


def mktmp():
    return tempfile.mkdtemp()


class TestReportGeneration:
    def test_daily_report_basic(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        # 写入测试事件
        for i in range(5):
            e = make_event(is_violence=(i < 2), violence_type="侮辱贬低类")
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        assert report["type"] == "daily"
        assert report["summary"]["total_events"] == 5
        assert report["summary"]["violence_count"] == 2
        assert report["summary"]["violence_rate"] == 40.0
        shutil.rmtree(tmp)

    def test_daily_report_no_events(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        report = engine.generate_daily_report()
        assert report["summary"]["total_events"] == 0
        assert report["summary"]["violence_count"] == 0
        shutil.rmtree(tmp)

    def test_daily_report_reads_legacy_timestamp_only_event(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        event = make_event(timestamp="2026-04-28 09:10:00", is_violence=True)
        event.pop("ts")
        with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report("2026-04-28")
        assert report["summary"]["total_events"] == 1
        assert report["summary"]["violence_count"] == 1
        shutil.rmtree(tmp)

    def test_hourly_breakdown(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        # 写入多条不同时段的事件
        for i in range(3):
            e = make_event(is_violence=True, violence_type="侮辱贬低类")
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        assert isinstance(report["hourly_breakdown"], dict)

    def test_violence_types(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for vt in ["侮辱贬低类", "威胁恐吓类", "侮辱贬低类"]:
            e = make_event(is_violence=True, violence_type=vt)
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        assert report["violence_types"]["侮辱贬低类"] == 2
        assert report["violence_types"]["威胁恐吓类"] == 1
        shutil.rmtree(tmp)

    def test_speaker_analysis(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for spk in ["user1", "user2", "user1"]:
            e = make_event(speaker=spk, is_violence=(spk == "user1"))
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        assert report["speakers"]["user1"]["violence"] == 2
        assert report["speakers"]["user1"]["events"] == 2
        assert report["speakers"]["user1"]["observation_level"] in {"normal", "watch", "high"}
        assert "心理状态诊断" in report["speaker_content_notice"]
        assert report["speakers"]["user2"]["violence"] == 0
        shutil.rmtree(tmp)

    def test_acoustic_alerts(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for i in range(3):
            e = make_event(acoustic_risk_score=70, volume_spike=True)
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        assert report["summary"]["acoustic_alerts"] == 3
        shutil.rmtree(tmp)

    def test_high_risk_periods(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        # 写入多个事件，确保有高风险时段
        for i in range(10):
            e = make_event(is_violence=(i < 5))
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        # 高风险时段应有内容（如果事件足够多）
        assert isinstance(report["high_risk_periods"], list)

    def test_save_and_load_report(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for i in range(3):
            e = make_event(is_violence=True)
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_daily_report()
        path = engine.save_report(report)
        assert os.path.exists(path)
        assert Path(path).stat().st_mode & 0o777 == 0o600
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["type"] == "daily"
        assert loaded["summary"]["violence_count"] == 3
        shutil.rmtree(tmp)

    def test_get_latest_reports(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for i in range(3):
            for j in range(2):
                e = make_event(is_violence=True)
                with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            engine.save_report(engine.generate_daily_report())
        reports = engine.get_latest_reports(limit=5)
        assert len(reports) == 3
        shutil.rmtree(tmp)

    def test_overview_30_days(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        for i in range(20):
            e = make_event(is_violence=(i % 3 == 0))
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        overview = engine.generate_overview(days=30)
        assert overview["total_events"] == 20
        assert overview["violence_count"] == 7  # 20/3 ≈ 7
        assert overview["period_days"] == 30
        assert len(overview["daily_trend_labels"]) <= 14  # 最多14天
        shutil.rmtree(tmp)

    def test_monthly_report_compares_previous_month(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        prior_ts = time.mktime((2026, 4, 10, 12, 0, 0, 0, 0, -1))
        current_ts = time.mktime((2026, 5, 10, 12, 0, 0, 0, 0, -1))
        for ts in [prior_ts, prior_ts, current_ts]:
            e = make_event(ts=ts, is_violence=True)
            with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        report = engine.generate_monthly_report(2026, 5)
        trend = report["trend_vs_previous"]
        assert trend["previous_violence"] == 2
        assert trend["current_violence"] == 1
        assert trend["delta"] == -1
        assert trend["trend"] == "down"
        shutil.rmtree(tmp)

    def test_weekly_report_honors_selected_anchor_date(self):
        tmp = mktmp()
        engine = TrendReportEngine(log_dir=tmp, data_dir=tmp)
        event_ts = time.mktime((2026, 5, 6, 12, 0, 0, 0, 0, -1))
        with open(Path(tmp) / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(make_event(ts=event_ts, is_violence=True), ensure_ascii=False) + "\n")
        report = engine.generate_weekly_report(anchor_date="2026-05-06")
        assert report["summary"]["total_events"] == 1
        assert report["period"]["start_str"].startswith("2026-05-04")
        shutil.rmtree(tmp)


if __name__ == "__main__":
    import traceback
    cls = TestReportGeneration
    inst = cls()
    total = passed = failed = 0
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

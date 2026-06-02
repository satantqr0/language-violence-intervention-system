#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势分析与报告引擎
支持日/周/月报告、时段分析、说话人画像、场景对比
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import statistics

from speaker_profile_engine import SpeakerProfileEngine


class TrendReportEngine:
    """趋势报告生成引擎"""

    def __init__(self, log_dir: str = "./logs", data_dir: str = "./data"):
        self.log_dir = Path(log_dir)
        self.data_dir = Path(data_dir)
        self.jsonl_file = self.log_dir / "events.jsonl"
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        for path in self.reports_dir.glob("*.json"):
            os.chmod(path, 0o600)
        self.profile_engine = SpeakerProfileEngine(str(self.log_dir), str(self.data_dir))

    def load_events(self, start_ts: float = 0, end_ts: float = float("inf")) -> List[Dict]:
        """加载指定时间范围内的事件"""
        events = []
        if not self.jsonl_file.exists():
            return events
        with open(self.jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    ts = e.get("ts")
                    if not ts and e.get("timestamp"):
                        ts = datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S").timestamp()
                        e["ts"] = ts
                    ts = ts or 0
                    if start_ts <= ts <= end_ts:
                        events.append(e)
                except:
                    continue
        return events

    def generate_daily_report(self, date_str: str = None) -> Dict:
        """
        生成单日报告

        Returns:
            {
                "type": "daily",
                "date": "2026-05-26",
                "period": {"start": ts, "end": ts},
                "summary": {
                    "total_events": 12,
                    "violence_count": 3,
                    "violence_rate": 25.0,
                    "intervention_count": 2,
                    "avg_confidence": 0.72,
                    "high_severity_count": 1,
                },
                "hourly_breakdown": {
                    "09": {"total": 5, "violence": 1},
                    "14": {"total": 7, "violence": 2},
                    ...
                },
                "violence_types": {
                    "侮辱贬低类": 2,
                    "威胁恐吓类": 1,
                },
                "scenes": {
                    "家庭": 8,
                    "夫妻": 4,
                },
                "speakers": {
                    "user1": {"events": 6, "violence": 2},
                    "user2": {"events": 6, "violence": 1},
                },
                "acoustic_alerts": 4,
                "trend_vs_yesterday": +1,  # 暴力事件数变化
                "high_risk_periods": ["09:00-10:00", "21:00-22:00"],
                "generated_at": timestamp
            }
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        start_dt = datetime.strptime(date_str, "%Y-%m-%d")
        end_dt = start_dt + timedelta(days=1)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp() - 1

        events = self.load_events(start_ts, end_ts)
        return self._build_report("daily", date_str, events, start_ts, end_ts)

    def generate_weekly_report(self, week_offset: int = 0, anchor_date: str = None) -> Dict:
        """生成包含锚点日期的周报（week_offset=0=锚点所在周）。"""
        anchor = datetime.strptime(anchor_date, "%Y-%m-%d") if anchor_date else datetime.now()
        today = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        # 本周一
        monday = today - timedelta(days=today.weekday())
        # 从 offset 周开始
        week_start = monday - timedelta(weeks=-week_offset)
        week_end = week_start + timedelta(days=7)
        start_ts = week_start.timestamp()
        end_ts = week_end.timestamp() - 1

        events = self.load_events(start_ts, end_ts)
        label = f"{(week_start + timedelta(days=6)).strftime('%Y-%m-%d')} 周报"
        return self._build_report("weekly", label, events, start_ts, end_ts)

    def generate_monthly_report(self, year: int = None, month: int = None) -> Dict:
        """生成月报"""
        if year is None or month is None:
            now = datetime.now()
            year, month = now.year, now.month

        start_dt = datetime(year, month, 1)
        end_dt = (start_dt + timedelta(days=32)).replace(day=1)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp() - 1

        events = self.load_events(start_ts, end_ts)
        label = f"{year}年{month}月月报"
        return self._build_report("monthly", label, events, start_ts, end_ts)

    def _build_report(self, report_type: str, label: str,
                      events: List[Dict], start_ts: float, end_ts: float) -> Dict:
        """构建报告结构"""
        total = len(events)
        violence_events = [e for e in events if e.get("is_violence")]
        interventions = [e for e in events if e.get("intervention_triggered")]
        violence_count = len(violence_events)
        rate = round(violence_count / total * 100, 1) if total > 0 else 0.0

        # 时段分析
        hourly = defaultdict(lambda: {"total": 0, "violence": 0, "intervention": 0})
        for e in events:
            try:
                hour = datetime.fromtimestamp(e.get("ts", 0)).strftime("%H")
                hourly[hour]["total"] += 1
                if e.get("is_violence"):
                    hourly[hour]["violence"] += 1
                if e.get("intervention_triggered"):
                    hourly[hour]["intervention"] += 1
            except:
                pass

        # 高风险时段（暴力频率最高的2小时）
        high_risk_hours = sorted(
            hourly.items(),
            key=lambda x: x[1]["violence"],
            reverse=True
        )[:2]
        high_risk_periods = [f"{h}:00-{h}:59" for h, _ in high_risk_hours if _["violence"] > 0]

        # 暴力类型分布
        violence_types = defaultdict(int)
        for e in violence_events:
            vt = e.get("violence_type") or "未知"
            violence_types[vt] += 1

        # 场景分布
        scenes = defaultdict(int)
        for e in events:
            s = e.get("scene") or "未知"
            scenes[s] += 1

        # 声学预警统计
        acoustic_alerts = sum(
            1 for e in events
            if (e.get("acoustic_risk_score", 0) or 0) >= 60 or e.get("volume_spike")
        )

        # 情绪分布
        emotions = defaultdict(int)
        for e in events:
            em = e.get("emotion_type") or "未知"
            emotions[em] += 1

        # 置信度统计
        confidences = [e.get("violence_confidence", 0) for e in events if e.get("violence_confidence", 0) > 0]
        avg_conf = round(statistics.mean(confidences), 3) if confidences else 0

        # 严重度分布
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for e in violence_events:
            sev = e.get("violence_severity") or "low"
            if sev in severity_counts:
                severity_counts[sev] += 1

        # 人员画像仅汇总可审计内容观察，不将身份模板或筛查结论混入趋势统计。
        event_profiles = [
            profile for profile in self.profile_engine.list_profiles(events)
            if profile["event_count"] > 0
        ]
        speakers = {
            profile["speaker_id"]: {
                "display_name": profile["display_name"],
                "events": profile["event_count"],
                "violence": profile["violence_count"],
                "violence_rate": profile["violence_rate"],
                "interventions": profile["intervention_count"],
                "acoustic_alerts": profile["acoustic_alert_count"],
                "top_emotion": profile["top_emotion"],
                "observation_level": profile["content_observation"]["level"],
            }
            for profile in event_profiles
        }
        observations = []
        if total:
            observations.append("人员统计仅汇总转写内容和互动风险事件，不包含声纹模板或心理量表结论。")
        missed_interventions = max(0, violence_count - len(interventions))
        if missed_interventions:
            observations.append(f"{missed_interventions} 起风险事件未记录语音干预，请复核阈值与音频输出。")
        if high_risk_periods:
            observations.append(f"高风险时段集中在 {'、'.join(high_risk_periods)}。")
        if event_profiles:
            riskiest = max(event_profiles, key=lambda profile: profile["violence_count"])
            if riskiest["violence_count"]:
                observations.append(
                    f"{riskiest['display_name']} 标签下记录到 {riskiest['violence_count']} 起风险事件。"
                )

        # 趋势对比（与前一天/上周/上月）
        trend_vs_prev = self._compute_trend(report_type, label, violence_count, start_ts)

        # 周内对比（仅日报）
        weekday_trend = None
        if report_type == "daily":
            weekday = datetime.strptime(label, "%Y-%m-%d").weekday()
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_trend = weekday_names[weekday]

        report = {
            "type": report_type,
            "label": label,
            "period": {
                "start": start_ts,
                "end": end_ts,
                "start_str": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M"),
                "end_str": datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M"),
            },
            "summary": {
                "total_events": total,
                "violence_count": violence_count,
                "violence_rate": rate,
                "intervention_count": len(interventions),
                "intervention_rate": round(len(interventions) / violence_count * 100, 1) if violence_count > 0 else 0,
                "avg_confidence": avg_conf,
                "high_severity_count": severity_counts["high"],
                "medium_severity_count": severity_counts["medium"],
                "acoustic_alerts": acoustic_alerts,
            },
            "hourly_breakdown": dict(hourly),
            "violence_types": dict(violence_types),
            "scenes": dict(scenes),
            "speakers": speakers,
            "speaker_content_notice": "人员风险画像仅为说话内容观察，不构成身份确认或心理状态诊断。",
            "observations": observations,
            "emotions": dict(emotions),
            "trend_vs_previous": trend_vs_prev,
            "high_risk_periods": high_risk_periods,
            "weekday": weekday_trend,
            "severity_distribution": severity_counts,
            "generated_at": time.time(),
            "generated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return report

    def _compute_trend(self, report_type: str, label: str, current_violence: int,
                       start_ts: float) -> Dict:
        """计算与上一周期的趋势变化"""
        prev_violence = 0
        prev_label = "上一周期"
        try:
            period_start = datetime.fromtimestamp(start_ts)
            if report_type == "daily":
                prev_start = period_start - timedelta(days=1)
                prev_end = period_start - timedelta(seconds=1)
                prev_label = prev_start.strftime("%Y-%m-%d")
            elif report_type == "weekly":
                prev_start = period_start - timedelta(days=7)
                prev_end = period_start - timedelta(seconds=1)
                prev_label = "上周"
            else:
                prev_end = period_start - timedelta(seconds=1)
                prev_start = prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                prev_label = "上月"
            prev_events = self.load_events(prev_start.timestamp(), prev_end.timestamp())
            prev_violence = sum(1 for e in prev_events if e.get("is_violence"))
        except Exception:
            pass

        delta = current_violence - prev_violence
        pct = round(delta / prev_violence * 100, 1) if prev_violence > 0 else (100.0 if current_violence > 0 else 0.0)

        return {
            "previous_label": prev_label,
            "previous_violence": prev_violence,
            "current_violence": current_violence,
            "delta": delta,
            "change_pct": pct,
            "trend": "up" if delta > 0 else ("down" if delta < 0 else "stable"),
        }

    def generate_overview(self, days: int = 30) -> Dict:
        """生成总览数据（最近N天）"""
        end_ts = datetime.now().timestamp()
        start_ts = (datetime.now() - timedelta(days=days)).timestamp()
        events = self.load_events(start_ts, end_ts)

        total = len(events)
        violence_count = sum(1 for e in events if e.get("is_violence"))

        # 最近7天每天的暴力事件数
        daily_counts = defaultdict(lambda: {"total": 0, "violence": 0})
        for e in events:
            day = datetime.fromtimestamp(e.get("ts", 0)).strftime("%Y-%m-%d")
            daily_counts[day]["total"] += 1
            if e.get("is_violence"):
                daily_counts[day]["violence"] += 1

        # 按日期排序
        sorted_days = sorted(daily_counts.keys())
        labels = sorted_days[-14:]  # 最近14天
        daily_total = [daily_counts[d]["total"] for d in labels]
        daily_violence = [daily_counts[d]["violence"] for d in labels]

        # 周均暴力率
        weekly_rates = []
        for i in range(0, len(sorted_days), 7):
            week_events = sorted_days[i:i+7]
            week_v = sum(daily_counts[d]["violence"] for d in week_events)
            week_t = sum(daily_counts[d]["total"] for d in week_events)
            if week_t > 0:
                weekly_rates.append(round(week_v / week_t * 100, 1))

        # 最暴力的一天
        most_violent_day = max(sorted_days, key=lambda d: daily_counts[d]["violence"]) if sorted_days else None

        return {
            "period_days": days,
            "total_events": total,
            "violence_count": violence_count,
            "violence_rate": round(violence_count / total * 100, 1) if total > 0 else 0,
            "daily_trend_labels": labels,
            "daily_trend_total": daily_total,
            "daily_trend_violence": daily_violence,
            "weekly_rates": weekly_rates,
            "most_violent_day": {
                "date": most_violent_day,
                "count": daily_counts[most_violent_day]["violence"] if most_violent_day else 0
            },
            "generated_at": time.time(),
        }

    def save_report(self, report: Dict) -> str:
        """保存报告到文件"""
        rtype = report.get("type", "report")
        label = report.get("label", datetime.now().strftime("%Y-%m-%d")).replace("/", "-")
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{rtype}_{label}_{ts_str}.json"
        path = self.reports_dir / filename
        with open(
            path,
            "w",
            encoding="utf-8",
            opener=lambda filename, flags: os.open(filename, flags, 0o600),
        ) as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        os.chmod(path, 0o600)
        return str(path)

    def get_latest_reports(self, limit: int = 10) -> List[Dict]:
        """获取最近的报告列表"""
        reports = []
        if not self.reports_dir.exists():
            return reports
        for p in sorted(self.reports_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                with open(p, encoding="utf-8") as f:
                    r = json.load(f)
                    r["_file"] = p.name
                    reports.append(r)
            except:
                continue
        return reports

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Observed-speaker profiles and manually maintained household records."""

import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional


UNKNOWN_SPEAKERS = {"", "unknown", "未知", "模拟用户"}
ATTENTION_LEVELS = {"normal", "watch", "priority"}
CONTENT_SIGNALS = {
    "痛苦或求助表达": [
        "撑不住", "崩溃", "睡不着", "失眠", "害怕", "焦虑", "难受",
        "孤独", "没有人帮", "好累", "太累了",
    ],
    "生命安全相关表达": [
        "不想活", "想死", "自杀", "结束生命", "伤害自己", "去死",
    ],
    "支持与修复表达": [
        "对不起", "我理解", "一起解决", "我陪你", "需要帮助",
        "谢谢你", "慢慢说",
    ],
}
COERCIVE_TYPES = {"侮辱贬低类", "威胁恐吓类", "情感操控类", "人身攻击类", "冷暴力类"}


class SpeakerProfileEngine:
    """Build auditable profiles from events and store non-biometric annotations."""

    def __init__(self, log_dir: str = "./logs", data_dir: str = "./data"):
        self.log_dir = Path(log_dir)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.data_dir / "speaker_registry.json"
        self.marks_file = self.log_dir / "event_marks.json"
        for path in (self.registry_file, self.marks_file):
            if path.exists():
                os.chmod(path, 0o600)

    def _load_registry(self) -> Dict[str, Dict]:
        if not self.registry_file.exists():
            return {}
        try:
            return json.loads(self.registry_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_registry(self, registry: Dict[str, Dict]):
        with open(
            self.registry_file,
            "w",
            encoding="utf-8",
            opener=lambda path, flags: os.open(path, flags, 0o600),
        ) as registry_file:
            registry_file.write(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
        os.chmod(self.registry_file, 0o600)

    def _load_marks(self) -> Dict[str, Dict]:
        if not self.marks_file.exists():
            return {}
        try:
            return json.loads(self.marks_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _speaker_id(event: Dict) -> str:
        return str(event.get("speaker") or "unknown")

    @staticmethod
    def _uncertain_identity(speaker_id: str) -> bool:
        lowered = speaker_id.strip().lower()
        return lowered in UNKNOWN_SPEAKERS or "模拟" in speaker_id

    @staticmethod
    def _mean(events: List[Dict], key: str) -> Optional[float]:
        values = [float(e[key]) for e in events if e.get(key) is not None]
        return round(mean(values), 1) if values else None

    @staticmethod
    def _top(events: List[Dict], key: str) -> Optional[Dict]:
        counts = Counter(str(e.get(key)) for e in events if e.get(key))
        if not counts:
            return None
        name, count = counts.most_common(1)[0]
        return {"name": name, "count": count}

    @staticmethod
    def _signal_matches(events: List[Dict], terms: List[str]) -> List[Dict]:
        matches = []
        for event in events:
            text = str(event.get("text") or "")
            hit = next((term for term in terms if term in text), None)
            if hit:
                matches.append({"event": event, "term": hit})
        return matches

    def _content_observation(self, events: List[Dict]) -> Dict:
        """Describe auditable language signals without inferring a diagnosis."""
        notice = (
            "自动观察仅归纳已记录的表达与互动风险，不等同于本人心理评估或医疗诊断。"
            "心理症状筛查须由本人自愿填写标准量表。"
        )
        if not events:
            return {
                "level": "insufficient",
                "label": "样本不足",
                "summary": "尚无关联说话内容，无法形成内容观察。",
                "notice": notice,
                "dimensions": [],
                "evidence": [],
                "requires_immediate_review": False,
            }

        violence = [event for event in events if event.get("is_violence")]
        coercive = [
            event for event in violence if str(event.get("violence_type") or "") in COERCIVE_TYPES
        ]
        high_severity = [
            event for event in violence if str(event.get("violence_severity") or "") == "high"
        ]
        tense = [
            event for event in events
            if float(event.get("emotion_score") or 0) >= 60
            or float(event.get("acoustic_risk_score") or 0) >= 60
        ]
        distress = self._signal_matches(events, CONTENT_SIGNALS["痛苦或求助表达"])
        safety = self._signal_matches(events, CONTENT_SIGNALS["生命安全相关表达"])
        supportive = self._signal_matches(events, CONTENT_SIGNALS["支持与修复表达"])
        event_count = len(events)
        violence_rate = round(len(violence) / event_count * 100, 1)

        if safety or high_severity or violence_rate >= 50:
            level, label = "high", "需优先人工复核"
        elif violence or distress or tense:
            level, label = "watch", "需持续观察"
        else:
            level, label = "normal", "暂无显著风险信号"

        def indicator(count: int, alert_at: int = 1) -> str:
            return "watch" if count >= alert_at else "normal"

        dimensions = [
            {
                "name": "互动攻击与控制",
                "level": "high" if high_severity else indicator(len(coercive)),
                "value": f"{len(coercive)} 条",
                "description": "侮辱、威胁、操控、人身攻击或冷处理相关事件",
            },
            {
                "name": "情绪与声学张力",
                "level": indicator(len(tense)),
                "value": f"{len(tense)} 条",
                "description": "情绪强度或声音风险指标升高的表达",
            },
            {
                "name": "痛苦或求助表达",
                "level": indicator(len(distress)),
                "value": f"{len(distress)} 条",
                "description": "仅标记文字线索，需结合本人沟通复核",
            },
            {
                "name": "生命安全相关表达",
                "level": "high" if safety else "normal",
                "value": f"{len(safety)} 条",
                "description": "出现时应立即由人工核实安全风险与支持需求",
            },
            {
                "name": "支持与修复表达",
                "level": "positive" if supportive else "neutral",
                "value": f"{len(supportive)} 条",
                "description": "道歉、理解、陪伴或共同解决等修复性表达",
            },
        ]

        evidence = []
        for match_group, signal_name in (
            (safety, "生命安全相关表达"),
            (distress, "痛苦或求助表达"),
            (supportive, "支持与修复表达"),
        ):
            for match in match_group:
                event = match["event"]
                evidence.append({
                    "timestamp": event.get("timestamp", ""),
                    "signal": signal_name,
                    "excerpt": str(event.get("text") or "")[:100],
                })
        for event in violence:
            evidence.append({
                "timestamp": event.get("timestamp", ""),
                "signal": str(event.get("violence_type") or "互动风险表达"),
                "excerpt": str(event.get("text") or "")[:100],
            })
        evidence = sorted(evidence, key=lambda item: item["timestamp"], reverse=True)[:6]

        summary = (
            f"分析 {event_count} 条表达，发现 {len(violence)} 条互动风险事件"
            f"（{violence_rate}%），{len(distress)} 条痛苦或求助文字线索，"
            f"{len(safety)} 条生命安全相关文字线索。"
        )
        return {
            "level": level,
            "label": label,
            "summary": summary,
            "notice": notice,
            "dimensions": dimensions,
            "evidence": evidence,
            "requires_immediate_review": bool(safety),
        }

    def has_record(self, speaker_id: str, events: List[Dict]) -> bool:
        registry = self._load_registry()
        return speaker_id in registry or any(self._speaker_id(e) == speaker_id for e in events)

    def list_profiles(self, events: List[Dict], learning_profiles: Optional[Dict] = None) -> List[Dict]:
        registry = self._load_registry()
        speaker_ids = {self._speaker_id(event) for event in events} | set(registry)
        profiles = [
            self.build_profile(speaker_id, events, (learning_profiles or {}).get(speaker_id))
            for speaker_id in speaker_ids
        ]
        return sorted(
            profiles,
            key=lambda item: (
                item["attention_level"] == "priority",
                item["attention_level"] == "watch",
                item["violence_count"],
                item["event_count"],
            ),
            reverse=True,
        )

    def build_profile(self, speaker_id: str, events: List[Dict],
                      learning_profile: Optional[Dict] = None) -> Dict:
        registry = self._load_registry()
        metadata = registry.get(speaker_id, {})
        speaker_events = [e for e in events if self._speaker_id(e) == speaker_id]
        violence_events = [e for e in speaker_events if e.get("is_violence")]
        interventions = [e for e in speaker_events if e.get("intervention_triggered")]
        acoustic_alerts = [
            e for e in speaker_events
            if (e.get("acoustic_risk_score", 0) or 0) >= 60 or e.get("volume_spike")
        ]
        high_severity = [e for e in violence_events if e.get("violence_severity") == "high"]
        marks = self._load_marks()
        speaker_marks = [
            marks.get(str(e.get("ts")), {}).get("mark")
            for e in speaker_events
            if marks.get(str(e.get("ts")), {}).get("mark")
        ]
        mark_counts = Counter(speaker_marks)
        learning_profile = learning_profile or {}
        source = metadata.get("source") or ("observed" if speaker_events else "manual")
        content_observation = self._content_observation(speaker_events)

        display_name = metadata.get("display_name", "").strip()
        if not display_name:
            display_name = "未识别说话人" if self._uncertain_identity(speaker_id) else speaker_id
        recent_events = []
        for event in sorted(speaker_events, key=lambda e: e.get("ts", 0), reverse=True)[:6]:
            recent_events.append({
                "ts": event.get("ts"),
                "timestamp": event.get("timestamp", ""),
                "text": str(event.get("text", ""))[:100],
                "is_violence": bool(event.get("is_violence")),
                "violence_type": event.get("violence_type") or "",
                "violence_severity": event.get("violence_severity") or "",
                "intervention_triggered": bool(event.get("intervention_triggered")),
            })

        event_count = len(speaker_events)
        violence_count = len(violence_events)
        return {
            "speaker_id": speaker_id,
            "name": speaker_id,
            "display_name": display_name,
            "relationship": metadata.get("relationship", ""),
            "attention_level": metadata.get("attention_level", "normal"),
            "notes": metadata.get("notes", ""),
            "source": source,
            "content_notice": content_observation["notice"],
            "content_observation": content_observation,
            "event_count": event_count,
            "violence_count": violence_count,
            "violence_rate": round(violence_count / event_count * 100, 1) if event_count else 0.0,
            "intervention_count": len(interventions),
            "intervention_rate": round(len(interventions) / violence_count * 100, 1) if violence_count else 0.0,
            "acoustic_alert_count": len(acoustic_alerts),
            "high_severity_count": len(high_severity),
            "avg_confidence": self._mean(violence_events, "violence_confidence"),
            "avg_emotion_score": self._mean(speaker_events, "emotion_score"),
            "avg_acoustic_risk": self._mean(speaker_events, "acoustic_risk_score"),
            "top_emotion": self._top(speaker_events, "emotion_type"),
            "top_scene": self._top(speaker_events, "scene"),
            "top_violence_type": self._top(violence_events, "violence_type"),
            "feedback_count": learning_profile.get("feedback_count", len(speaker_marks)),
            "false_positives": learning_profile.get("false_positives", mark_counts.get("false_positive", 0)),
            "false_negatives": learning_profile.get("false_negatives", mark_counts.get("doubt", 0)),
            "confirmed_count": mark_counts.get("confirmed", 0),
            "created_at": metadata.get("created_at", learning_profile.get("created_at", "")),
            "updated_at": metadata.get("updated_at", ""),
            "first_seen": min((e.get("timestamp", "") for e in speaker_events), default=""),
            "last_seen": max((e.get("timestamp", "") for e in speaker_events), default=""),
            "recent_events": recent_events,
        }

    def create_profile(self, updates: Dict) -> str:
        speaker_id = f"manual-{uuid.uuid4().hex[:10]}"
        self.update_profile(speaker_id, updates, source="manual")
        return speaker_id

    def update_profile(self, speaker_id: str, updates: Dict, source: Optional[str] = None):
        registry = self._load_registry()
        current = registry.get(speaker_id, {})
        display_name = str(updates.get("display_name", current.get("display_name", ""))).strip()[:40]
        if not display_name:
            raise ValueError("请输入档案名称")
        relationship = str(updates.get("relationship", current.get("relationship", ""))).strip()[:30]
        notes = str(updates.get("notes", current.get("notes", ""))).strip()[:300]
        attention_level = str(updates.get("attention_level", current.get("attention_level", "normal")))
        if attention_level not in ATTENTION_LEVELS:
            raise ValueError("无效的关注级别")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        registry[speaker_id] = {
            "display_name": display_name,
            "relationship": relationship,
            "notes": notes,
            "attention_level": attention_level,
            "source": source or current.get("source", "observed"),
            "created_at": current.get("created_at", now),
            "updated_at": now,
        }
        self._save_registry(registry)

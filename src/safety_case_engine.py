#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local audit workflow for events that require prompt human safety review."""

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List


class SafetyCaseError(ValueError):
    """Raised when a safety review operation is invalid."""


class SafetyCaseEngine:
    """Track human review and actions separately from automatic interventions."""

    STATUSES = {"pending", "acknowledged", "resolved", "dismissed"}
    ACTIONS = {
        "",
        "contacted_subject",
        "contacted_trusted_person",
        "contacted_emergency_services",
        "referred_professional",
        "monitoring",
        "no_immediate_risk",
    }
    SAFETY_TERMS = (
        "不想活",
        "想死",
        "自杀",
        "结束生命",
        "伤害自己",
        "去死",
    )

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.data_dir / "safety_cases.json"
        if self.storage_file.exists():
            os.chmod(self.storage_file, 0o600)

    def _load(self) -> Dict[str, Dict]:
        if not self.storage_file.exists():
            return {}
        try:
            records = json.loads(self.storage_file.read_text(encoding="utf-8"))
            return records if isinstance(records, dict) else {}
        except Exception:
            return {}

    def _save(self, records: Dict[str, Dict]):
        handle, temporary_name = tempfile.mkstemp(
            prefix="safety_cases_", suffix=".json", dir=str(self.data_dir)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary_file:
                json.dump(records, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.storage_file)
            os.chmod(self.storage_file, 0o600)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @classmethod
    def _safety_terms(cls, text: str) -> List[str]:
        return [term for term in cls.SAFETY_TERMS if term in text]

    @classmethod
    def _event_reasons(cls, event: Dict) -> List[str]:
        reasons = []
        if event.get("is_violence") and event.get("violence_severity") == "high":
            reasons.append("高严重度互动风险")
        if cls._safety_terms(str(event.get("text") or "")):
            reasons.append("生命安全相关表达")
        return reasons

    @staticmethod
    def _case_sort_key(item: Dict):
        open_rank = 1 if item.get("status") in {"pending", "acknowledged"} else 0
        return (open_rank, str(item.get("timestamp") or item.get("created_at") or ""))

    def _event_candidates(self, events: List[Dict], stored: Dict[str, Dict]) -> Dict[str, Dict]:
        candidates = {}
        for event in events:
            reasons = self._event_reasons(event)
            ts = event.get("ts")
            if not reasons or ts is None:
                continue
            case_id = f"event:{ts}"
            saved = stored.get(case_id, {})
            candidates[case_id] = {
                "id": case_id,
                "source": "event",
                "trigger": "、".join(reasons),
                "priority": "immediate" if "生命安全相关表达" in reasons else "high",
                "timestamp": event.get("timestamp", ""),
                "speaker": event.get("speaker", ""),
                "scene": event.get("scene", ""),
                "severity": event.get("violence_severity", ""),
                "text": str(event.get("text") or "")[:160],
                "status": saved.get("status", "pending"),
                "action": saved.get("action", ""),
                "note": saved.get("note", ""),
                "created_at": saved.get("created_at", event.get("timestamp", "")),
                "updated_at": saved.get("updated_at", ""),
                "history": saved.get("history", []),
            }
        return candidates

    def _all_cases(self, events: List[Dict]) -> Dict[str, Dict]:
        stored = self._load()
        cases = self._event_candidates(events, stored)
        for case_id, saved in stored.items():
            if case_id not in cases:
                cases[case_id] = dict(saved)
        return cases

    def list_cases(self, events: List[Dict], limit: int = 50) -> Dict:
        cases = list(self._all_cases(events).values())
        cases.sort(key=self._case_sort_key, reverse=True)
        summary = {status: 0 for status in self.STATUSES}
        for case in cases:
            status = case.get("status", "pending")
            if status in summary:
                summary[status] += 1
        summary["open"] = summary["pending"] + summary["acknowledged"]
        return {
            "ok": True,
            "summary": summary,
            "cases": cases[:max(1, min(int(limit), 200))],
        }

    def create_screening_alert(self, speaker_id: str, screening: Dict) -> Dict:
        """Create an alert without persisting item-level answers or a diagnosis."""
        if not screening.get("urgent"):
            raise SafetyCaseError("筛查结果未产生紧急安全复核事项")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        case_id = f"screening:{uuid.uuid4().hex}"
        case = {
            "id": case_id,
            "source": "screening",
            "trigger": "本人自愿筛查提示生命安全风险",
            "priority": "immediate",
            "timestamp": screening.get("submitted_at", now),
            "speaker": str(speaker_id),
            "scene": "",
            "severity": "high",
            "text": "本人自愿筛查出现需立即关注的生命安全相关自报。",
            "status": "pending",
            "action": "",
            "note": "",
            "created_at": now,
            "updated_at": "",
            "history": [],
        }
        records = self._load()
        records[case_id] = case
        self._save(records)
        return case

    def update_case(self, case_id: str, events: List[Dict], updates: Dict, actor: str) -> Dict:
        cases = self._all_cases(events)
        if case_id not in cases:
            raise SafetyCaseError("安全处置事项不存在")
        status = str(updates.get("status") or "").strip()
        action = str(updates.get("action") or "").strip()
        note = str(updates.get("note") or "").strip()[:500]
        if status not in self.STATUSES:
            raise SafetyCaseError("无效的处置状态")
        if action not in self.ACTIONS:
            raise SafetyCaseError("无效的处置措施")
        if status in {"resolved", "dismissed"} and (not action or not note):
            raise SafetyCaseError("完成处置或排除风险时，请填写措施和处置说明")

        current = cases[case_id]
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        history = list(current.get("history", []))
        history.append({
            "status": status,
            "action": action,
            "note": note,
            "actor": str(actor or "console")[:40],
            "updated_at": now,
        })
        saved = {
            key: current.get(key, "")
            for key in (
                "id", "source", "trigger", "priority", "timestamp",
                "speaker", "scene", "severity", "created_at",
            )
        }
        # Keep only a generic message for screening alerts; event text remains in its source log.
        if current.get("source") == "screening":
            saved["text"] = current.get("text", "")
        saved.update({
            "status": status,
            "action": action,
            "note": note,
            "updated_at": now,
            "history": history[-50:],
        })
        records = self._load()
        records[case_id] = saved
        self._save(records)
        result = dict(current)
        result.update(saved)
        return result

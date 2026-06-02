#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voluntary self-report mental wellbeing screening with local score storage."""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List


class ScreeningError(ValueError):
    """Raised when a voluntary screening submission is invalid."""


class MentalScreeningEngine:
    """Score self-reported PHQ-9 and GAD-7 without making a diagnosis."""

    OPTIONS = [
        {"value": 0, "label": "完全没有"},
        {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上天数"},
        {"value": 3, "label": "几乎每天"},
    ]
    INSTRUMENTS = {
        "phq9": {
            "id": "phq9",
            "name": "PHQ-9",
            "focus": "抑郁症状自报筛查",
            "period": "过去两周",
            "questions": [
                "做事时提不起劲或没有兴趣",
                "感到心情低落、沮丧或绝望",
                "入睡困难、睡不安稳或睡眠过多",
                "感觉疲倦或没有活力",
                "食欲不振或吃得太多",
                "觉得自己很糟糕，或觉得失败、让自己或家人失望",
                "对事物专注有困难，例如阅读或看电视",
                "动作或说话变慢到别人能察觉，或相反地烦躁、坐立不安",
                "有不如死掉或用某种方式伤害自己的念头",
            ],
            "bands": [
                (4, "极少或无相关症状自报", "normal"),
                (9, "轻度相关症状自报", "watch"),
                (14, "中度相关症状自报", "attention"),
                (19, "中重度相关症状自报", "attention"),
                (27, "重度相关症状自报", "attention"),
            ],
            "urgent_item": 8,
        },
        "gad7": {
            "id": "gad7",
            "name": "GAD-7",
            "focus": "焦虑症状自报筛查",
            "period": "过去两周",
            "questions": [
                "感到紧张、焦虑或急切",
                "不能停止或控制担忧",
                "对各种事情担忧过多",
                "很难放松下来",
                "由于不安而无法静坐",
                "变得容易烦恼或急躁",
                "感到似乎将有可怕的事情发生而害怕",
            ],
            "bands": [
                (4, "极少或无焦虑症状自报", "normal"),
                (9, "轻度焦虑症状自报", "watch"),
                (14, "中度焦虑症状自报", "attention"),
                (21, "重度焦虑症状自报", "attention"),
            ],
        },
    }

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.data_dir / "mental_screenings.json"
        if self.storage_file.exists():
            os.chmod(self.storage_file, 0o600)

    def instruments(self) -> List[Dict]:
        return [
            {
                "id": definition["id"],
                "name": definition["name"],
                "focus": definition["focus"],
                "period": definition["period"],
                "questions": definition["questions"],
                "options": self.OPTIONS,
            }
            for definition in self.INSTRUMENTS.values()
        ]

    def _load(self) -> Dict[str, List[Dict]]:
        if not self.storage_file.exists():
            return {}
        try:
            data = json.loads(self.storage_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, results: Dict[str, List[Dict]]):
        handle, temporary_name = tempfile.mkstemp(
            prefix="mental_screenings_", suffix=".json", dir=str(self.data_dir)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary_file:
                json.dump(results, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.storage_file)
            os.chmod(self.storage_file, 0o600)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @classmethod
    def _band(cls, instrument: str, score: int) -> Dict:
        for ceiling, label, level in cls.INSTRUMENTS[instrument]["bands"]:
            if score <= ceiling:
                return {"label": label, "level": level}
        raise ScreeningError("量表得分范围异常")

    def submit(self, speaker_id: str, instrument: str, answers: List[int],
               consent: bool, self_report: bool) -> Dict:
        if not consent or not self_report:
            raise ScreeningError("仅可在本人自愿填写并同意保存结果后提交筛查")
        if instrument not in self.INSTRUMENTS:
            raise ScreeningError("不支持的筛查量表")
        definition = self.INSTRUMENTS[instrument]
        if not isinstance(answers, list) or len(answers) != len(definition["questions"]):
            raise ScreeningError("请完整回答全部条目")
        try:
            values = [int(answer) for answer in answers]
        except (TypeError, ValueError) as exc:
            raise ScreeningError("量表答案无效") from exc
        if any(value < 0 or value > 3 for value in values):
            raise ScreeningError("量表答案无效")

        score = sum(values)
        band = self._band(instrument, score)
        urgent = bool(definition.get("urgent_item") is not None and values[definition["urgent_item"]] > 0)
        if urgent:
            guidance = "存在生命安全相关自报，请立即由本人获得专业支持；若有即时危险，请联系急救或报警求助。"
        elif score >= 10:
            guidance = "筛查分值提示值得进一步关注，建议由本人联系专业心理或精神卫生服务复核。"
        else:
            guidance = "结果仅供本人了解近期感受；如持续困扰或影响生活，建议主动寻求专业支持。"
        result = {
            "instrument": instrument,
            "name": definition["name"],
            "focus": definition["focus"],
            "score": score,
            "max_score": len(values) * 3,
            "severity": band["label"],
            "level": "urgent" if urgent else band["level"],
            "urgent": urgent,
            "guidance": guidance,
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "basis": "本人自愿自报",
            "diagnostic": False,
        }
        results = self._load()
        history = results.setdefault(str(speaker_id), [])
        history.append(result)
        results[str(speaker_id)] = history[-24:]
        self._save(results)
        return result

    def summary(self, speaker_id: str) -> Dict:
        history = self._load().get(str(speaker_id), [])
        latest = {}
        for result in history:
            latest[result["instrument"]] = result
        return {
            "latest": latest,
            "history_count": len(history),
            "notice": "标准量表仅可由本人自愿填写，结果属于筛查提示，不构成医疗诊断。",
            "reference": (
                "国家卫生健康委《消防救援人员职业健康保护指南》"
                "（GBZ/T 343-2026，2026-07-01 实施）附录 G 列示 "
                "PHQ-9 / GAD-7；仅作量表出处参考，不作为家庭个案诊断依据。"
            ),
        }

    def clear(self, speaker_id: str) -> bool:
        results = self._load()
        key = str(speaker_id)
        if key not in results:
            return False
        del results[key]
        self._save(results)
        return True

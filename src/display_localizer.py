#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Translate internal event enums at human-facing output boundaries."""

from typing import Any


FIELD_LABELS = {
    "emotion_type": {
        "unknown": "未知",
    },
    "emotion_intensity": {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无",
        "unknown": "未知",
    },
    "violence_type": {
        "unknown": "未分类",
    },
    "violence_severity": {
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
        "none": "无风险",
        "unknown": "未知",
    },
    "speaker": {
        "unknown": "未识别说话人",
        "未知": "未识别说话人",
    },
    "scene": {
        "unknown": "未知场景",
    },
    "volume_level": {
        "shouting": "喊叫",
        "loud": "偏大",
        "normal": "正常",
        "quiet": "安静",
        "unknown": "未知",
    },
    "pitch_trend": {
        "rising": "升高",
        "falling": "降低",
        "stable": "平稳",
        "unknown": "未知",
    },
}

BOOLEAN_FIELDS = {
    "is_violence",
    "speaker_verified",
    "intervention_triggered",
    "volume_spike",
}


def display_value(field: str, value: Any) -> Any:
    """Return a Chinese display value while keeping stored event data untouched."""
    if value is None:
        return ""
    if field in BOOLEAN_FIELDS and isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "；".join(str(display_value(field, item)) for item in value)
    if isinstance(value, dict):
        return "；".join(f"{key}: {display_value(field, item)}" for key, item in value.items())
    text = str(value)
    return FIELD_LABELS.get(field, {}).get(text, value)

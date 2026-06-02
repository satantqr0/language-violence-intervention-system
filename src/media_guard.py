#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locally calibrated acoustic gate for recurring TV and music playback."""

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List

import numpy as np


class MediaGuardError(ValueError):
    """Raised when media calibration or configuration is invalid."""


class MediaGuard:
    """Suppress high-confidence playback matches before speech transcription."""

    KINDS = {"media", "human"}
    MODES = {"balanced", "strict"}
    MAX_TEMPLATES = 6

    def __init__(
        self,
        data_dir: str = "./data",
        sample_rate: int = 16000,
        enabled: bool = True,
        mode: str = "balanced",
        match_margin: float = 0.035,
        max_media_distance: float = 0.17,
        shouting_bypass_rms: float = 2500.0,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = int(sample_rate)
        self.enabled = bool(enabled)
        self.mode = mode if mode in self.MODES else "balanced"
        self.match_margin = float(match_margin)
        self.max_media_distance = float(max_media_distance)
        self.shouting_bypass_rms = float(shouting_bypass_rms)
        self.templates_file = self.data_dir / "media_guard_templates.json"
        self.stats_file = self.data_dir / "media_guard_stats.json"
        for path in (self.templates_file, self.stats_file):
            if path.exists():
                os.chmod(path, 0o600)

    def load(self):
        status = self.status()
        print(
            "   媒体声过滤已启用"
            if self.enabled
            else "   媒体声过滤未启用"
        )
        if self.enabled and not status["ready"]:
            print("   媒体声过滤待校准（校准前不会屏蔽语音）")

    @staticmethod
    def _read_json(path: Path, default: Dict) -> Dict:
        if not path.exists():
            return default
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
        except Exception:
            return default

    @staticmethod
    def _private_write(path: Path, value: Dict):
        handle, temporary_name = tempfile.mkstemp(
            prefix=path.stem + "_", suffix=".json", dir=str(path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary_file:
                json.dump(value, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _templates(self) -> Dict[str, List[Dict]]:
        stored = self._read_json(self.templates_file, {})
        return {
            "media": stored.get("media", []) if isinstance(stored.get("media", []), list) else [],
            "human": stored.get("human", []) if isinstance(stored.get("human", []), list) else [],
        }

    def _frames(self, audio: np.ndarray) -> List[np.ndarray]:
        frame_size = max(512, int(self.sample_rate * 0.25))
        frames = []
        for start in range(0, len(audio) - frame_size + 1, frame_size):
            frames.append(audio[start:start + frame_size])
        return frames

    def extract_features(self, audio: np.ndarray) -> List[float]:
        """Compute a compact playback fingerprint; raw audio is never persisted."""
        if audio is None or len(audio) < self.sample_rate // 2:
            raise MediaGuardError("采集声音过短，请保持声音至少 1 秒")
        frames = self._frames(np.asarray(audio, dtype=np.float32) / 32768.0)
        if len(frames) < 2:
            raise MediaGuardError("声音样本不足，无法完成校准")
        per_frame = []
        previous_spectrum = None
        for frame in frames:
            windowed = frame * np.hanning(len(frame))
            spectrum = np.abs(np.fft.rfft(windowed)) + 1e-10
            power = spectrum ** 2
            norm_power = power / float(np.sum(power))
            bins = np.linspace(0.0, 1.0, len(norm_power))
            rms = float(np.sqrt(np.mean(frame ** 2)))
            rms_scaled = float(np.clip((20 * np.log10(rms + 1e-8) + 80) / 80, 0, 1))
            zcr = float(np.mean(frame[:-1] * frame[1:] < 0))
            centroid = float(np.sum(bins * norm_power))
            rolloff = float(bins[int(np.searchsorted(np.cumsum(norm_power), 0.85))])
            flatness = float(np.exp(np.mean(np.log(power))) / np.mean(power))
            dominant = float(np.max(norm_power))
            flux = 0.0 if previous_spectrum is None else float(
                np.mean(np.abs(norm_power - previous_spectrum))
            )
            previous_spectrum = norm_power
            per_frame.append([rms_scaled, zcr, centroid, rolloff, flatness, dominant, flux])
        features = np.asarray(per_frame, dtype=np.float64)
        vector = np.concatenate([features.mean(axis=0), features.std(axis=0)])
        return [round(float(value), 6) for value in vector]

    @staticmethod
    def _distance(left: List[float], right: List[float]) -> float:
        a = np.asarray(left, dtype=np.float64)
        b = np.asarray(right, dtype=np.float64)
        if a.shape != b.shape or not len(a):
            return float("inf")
        return float(np.linalg.norm(a - b) / math.sqrt(len(a)))

    def calibrate(self, kind: str, audio: np.ndarray, consent: bool = False) -> Dict:
        kind = str(kind or "").strip()
        if kind not in self.KINDS:
            raise MediaGuardError("请选择媒体播放或真人语音样本")
        if kind == "human" and consent is not True:
            raise MediaGuardError("采集真人语音样本前需取得本人知情同意")
        vector = self.extract_features(audio)
        templates = self._templates()
        templates[kind] = (templates[kind] + [{
            "features": vector,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }])[-self.MAX_TEMPLATES:]
        self._private_write(self.templates_file, templates)
        return self.status()

    def clear(self, kind: str) -> Dict:
        if kind not in self.KINDS:
            raise MediaGuardError("无效的样本类别")
        templates = self._templates()
        templates[kind] = []
        self._private_write(self.templates_file, templates)
        return self.status()

    def classify(self, audio: np.ndarray) -> Dict:
        rms = float(np.sqrt(np.mean(np.asarray(audio, dtype=np.float32) ** 2))) if audio is not None and len(audio) else 0.0
        result = {
            "enabled": self.enabled,
            "ready": False,
            "suppressed": False,
            "decision": "pass",
            "reason": "disabled" if not self.enabled else "calibration_required",
            "rms": round(rms, 1),
        }
        if not self.enabled:
            return result
        templates = self._templates()
        if not templates["media"] or not templates["human"]:
            return result
        result["ready"] = True
        try:
            vector = self.extract_features(audio)
        except MediaGuardError:
            result["reason"] = "sample_too_short"
            return result
        media_distance = min(self._distance(vector, item["features"]) for item in templates["media"])
        human_distance = min(self._distance(vector, item["features"]) for item in templates["human"])
        required_margin = self.match_margin if self.mode == "balanced" else self.match_margin * 0.55
        max_distance = self.max_media_distance if self.mode == "balanced" else self.max_media_distance * 1.2
        result.update({
            "media_distance": round(media_distance, 4),
            "human_distance": round(human_distance, 4),
            "confidence_margin": round(human_distance - media_distance, 4),
        })
        if rms >= self.shouting_bypass_rms:
            result["reason"] = "loud_voice_bypass"
        elif media_distance <= max_distance and human_distance - media_distance >= required_margin:
            result.update({
                "suppressed": True,
                "decision": "media",
                "reason": "calibrated_media_match",
            })
        else:
            result["reason"] = "not_high_confidence_media"
        return result

    def record_suppression(self, decision: Dict):
        stats = self._read_json(self.stats_file, {})
        stats["filtered_count"] = int(stats.get("filtered_count", 0)) + 1
        stats["last_filtered_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        stats["last_reason"] = decision.get("reason", "")
        self._private_write(self.stats_file, stats)

    def status(self) -> Dict:
        templates = self._templates()
        stats = self._read_json(self.stats_file, {})
        return {
            "ok": True,
            "enabled": self.enabled,
            "mode": self.mode,
            "ready": bool(templates["media"] and templates["human"]),
            "media_samples": len(templates["media"]),
            "human_samples": len(templates["human"]),
            "filtered_count": int(stats.get("filtered_count", 0)),
            "last_filtered_at": stats.get("last_filtered_at", ""),
            "storage": "local_features_only",
            "shouting_bypass_rms": self.shouting_bypass_rms,
        }

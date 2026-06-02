#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local voiceprint enrollment and identification using ECAPA-TDNN embeddings."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np


class VoiceprintError(RuntimeError):
    """Raised for recoverable voiceprint workflow failures."""


class VoiceprintEngine:
    """Persist local speaker templates and match utterances against them."""

    MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
    SAMPLE_RATE = 16000

    def __init__(
        self,
        data_dir: str = "./data",
        model_dir: str = "./models/spkrec-ecapa-voxceleb",
        match_threshold: float = 0.45,
        max_speakers: int = 8,
        max_templates_per_speaker: int = 3,
        extractor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ):
        self.data_dir = Path(data_dir)
        self.model_dir = Path(model_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.voiceprints_file = self.data_dir / "voiceprints.json"
        self.match_threshold = float(match_threshold)
        self.max_speakers = int(max_speakers)
        self.max_templates_per_speaker = int(max_templates_per_speaker)
        self._external_extractor = extractor
        self._state_lock = threading.RLock()
        self.encoder = None
        self.loaded = extractor is not None
        self.load_error = ""
        self.voiceprints = self._load_voiceprints()

    def load(self) -> bool:
        """Load the embedding model only when it will be used."""
        with self._state_lock:
            if self.loaded:
                return True
            if not self.voiceprints:
                print("   声纹识别已就绪，尚无已注册声纹")
                return True
            return self._load_encoder()

    def prepare(self) -> bool:
        """Download/load the model before a user-triggered enrollment."""
        with self._state_lock:
            return self._load_encoder()

    def refresh_templates(self):
        """See templates persisted by another service process."""
        with self._state_lock:
            self.voiceprints = self._load_voiceprints()

    def _load_encoder(self) -> bool:
        with self._state_lock:
            if self.loaded:
                return True
            try:
                import torch
                from speechbrain.inference.speaker import EncoderClassifier

                torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
                self.model_dir.mkdir(parents=True, exist_ok=True)
                self.encoder = EncoderClassifier.from_hparams(
                    source=self.MODEL_SOURCE,
                    savedir=str(self.model_dir),
                    run_opts={"device": "cpu"},
                )
                self.loaded = True
                self.load_error = ""
                print("   声纹识别模型已加载 (ECAPA-TDNN, 本地推理)")
                return True
            except Exception as exc:
                self.load_error = str(exc)
                print(f"   声纹识别模型加载失败: {exc}")
                return False

    def _load_voiceprints(self) -> Dict[str, Dict]:
        if not self.voiceprints_file.exists():
            return {}
        try:
            data = json.loads(self.voiceprints_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_voiceprints(self):
        with self._state_lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(
                prefix="voiceprints_", suffix=".json", dir=str(self.data_dir)
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as temporary_file:
                    json.dump(self.voiceprints, temporary_file, ensure_ascii=False, indent=2)
                    temporary_file.write("\n")
                os.chmod(temporary_name, 0o600)
                os.replace(temporary_name, self.voiceprints_file)
                os.chmod(self.voiceprints_file, 0o600)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)

    @staticmethod
    def _validate_speaker_id(speaker_id: str):
        if not speaker_id or speaker_id.strip().lower() in {"unknown", "未知", "模拟用户"}:
            raise VoiceprintError("请先创建具名人员档案，再为其注册声纹")

    @classmethod
    def _validate_audio(cls, audio: np.ndarray, minimum_seconds: float = 2.0):
        if audio is None or len(audio) < cls.SAMPLE_RATE * minimum_seconds:
            raise VoiceprintError(f"有效语音不足 {minimum_seconds:.0f} 秒，请靠近麦克风重新采集")
        rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        if rms < 120:
            raise VoiceprintError("采集到的音量过低，请重新采集")

    @staticmethod
    def _normalize(embedding: np.ndarray) -> np.ndarray:
        values = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(values))
        if not norm:
            raise VoiceprintError("无法提取有效声纹特征")
        return values / norm

    def _extract_embedding(self, audio: np.ndarray) -> np.ndarray:
        self._validate_audio(audio)
        if self._external_extractor:
            return self._normalize(self._external_extractor(audio))
        if not self._load_encoder():
            raise VoiceprintError(f"声纹模型不可用: {self.load_error}")
        try:
            import torch

            signal = torch.from_numpy(audio.astype(np.float32) / 32768.0).unsqueeze(0)
            with torch.inference_mode():
                embedding = self.encoder.encode_batch(signal).squeeze().detach().cpu().numpy()
            return self._normalize(embedding)
        except VoiceprintError:
            raise
        except Exception as exc:
            raise VoiceprintError(f"声纹特征提取失败: {exc}") from exc

    def enroll(self, speaker_id: str, audio: np.ndarray) -> Dict:
        """Add a local biometric template for a named profile."""
        with self._state_lock:
            speaker_id = str(speaker_id).strip()
            self._validate_speaker_id(speaker_id)
            if speaker_id not in self.voiceprints and len(self.voiceprints) >= self.max_speakers:
                raise VoiceprintError(f"声纹容量已满（最多 {self.max_speakers} 人）")
            embedding = self._extract_embedding(audio)
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            record = self.voiceprints.get(speaker_id, {
                "speaker_id": speaker_id,
                "created_at": now,
                "templates": [],
            })
            record["templates"] = (record.get("templates", []) + [embedding.tolist()])[-self.max_templates_per_speaker:]
            record["updated_at"] = now
            record["sample_count"] = len(record["templates"])
            record["last_sample_seconds"] = round(len(audio) / self.SAMPLE_RATE, 1)
            record["model"] = self.MODEL_SOURCE
            self.voiceprints[speaker_id] = record
            self._save_voiceprints()
            return self.get_speaker_status(speaker_id)

    def register(self, speaker_id: str, audio: np.ndarray) -> bool:
        """Compatibility wrapper for older callers."""
        try:
            self.enroll(speaker_id, audio)
            return True
        except VoiceprintError as exc:
            print(f"声纹注册失败: {exc}")
            return False

    def identify_with_score(self, audio: np.ndarray) -> Dict:
        """Identify a speaker and return the match score and decision context."""
        with self._state_lock:
            unknown = {
                "speaker_id": "unknown",
                "matched": False,
                "score": 0.0,
                "threshold": self.match_threshold,
                "source": "voiceprint",
            }
            if not self.voiceprints:
                return unknown
            try:
                embedding = self._extract_embedding(audio)
            except VoiceprintError as exc:
                result = dict(unknown)
                result["error"] = str(exc)
                return result

            best_speaker = "unknown"
            best_score = -1.0
            for speaker_id, record in self.voiceprints.items():
                templates = record.get("templates", [])
                if not templates:
                    continue
                centroid = self._normalize(np.mean([np.asarray(t, dtype=np.float32) for t in templates], axis=0))
                score = float(np.dot(embedding, centroid))
                if score > best_score:
                    best_speaker = speaker_id
                    best_score = score
            score = round(max(0.0, best_score), 4)
            if best_score >= self.match_threshold:
                return {
                    "speaker_id": best_speaker,
                    "matched": True,
                    "score": score,
                    "threshold": self.match_threshold,
                    "source": "voiceprint",
                }
            result = dict(unknown)
            result["score"] = score
            return result

    def identify(self, audio: np.ndarray) -> str:
        return self.identify_with_score(audio)["speaker_id"]

    def get_speaker_status(self, speaker_id: str) -> Dict:
        with self._state_lock:
            record = self.voiceprints.get(speaker_id)
            if not record:
                return {
                    "speaker_id": speaker_id,
                    "enrolled": False,
                    "sample_count": 0,
                    "ready": False,
                }
            sample_count = len(record.get("templates", []))
            return {
                "speaker_id": speaker_id,
                "enrolled": sample_count > 0,
                "sample_count": sample_count,
                "recommended_samples": self.max_templates_per_speaker,
                "ready": sample_count > 0,
                "created_at": record.get("created_at", ""),
                "updated_at": record.get("updated_at", ""),
                "last_sample_seconds": record.get("last_sample_seconds"),
                "model": record.get("model", self.MODEL_SOURCE),
            }

    def status(self) -> Dict:
        with self._state_lock:
            return {
                "ok": True,
                "engine": "ecapa_tdnn",
                "model": self.MODEL_SOURCE,
                "storage": "local_embedding_only",
                "match_threshold": self.match_threshold,
                "speaker_count": len(self.voiceprints),
                "max_speakers": self.max_speakers,
                "speakers": [
                    self.get_speaker_status(speaker_id)
                    for speaker_id in sorted(self.voiceprints)
                ],
                "loaded": self.loaded,
                "load_error": self.load_error,
            }

    def remove(self, speaker_id: str) -> bool:
        with self._state_lock:
            if speaker_id not in self.voiceprints:
                return False
            del self.voiceprints[speaker_id]
            self._save_voiceprints()
            return True

    def list_speakers(self) -> List[str]:
        with self._state_lock:
            return sorted(self.voiceprints)

    def clear(self):
        with self._state_lock:
            self.voiceprints.clear()
            self._save_voiceprints()


class SpeakerDiarization:
    """Single-segment placeholder; identity is resolved through registered templates."""

    def __init__(self, max_speakers: int = 4):
        self.max_speakers = max_speakers

    def segment(self, audio: np.ndarray, sample_rate: int = 16000) -> List[Dict]:
        duration = len(audio) / sample_rate
        return [{"speaker": 0, "start": 0.0, "end": duration}]

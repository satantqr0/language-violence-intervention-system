#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
识别学习引擎 - 通过用户反馈持续优化检测准确性
"""
import json
import os
import time
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import statistics

class LearningEngine:
    """学习引擎：收集反馈、分析模式、优化参数"""
    
    def __init__(self, data_dir: str = None):
        default_data_dir = Path(__file__).resolve().parent.parent / "data"
        self.data_dir = Path(data_dir or os.getenv("VD_DATA_DIR", str(default_data_dir)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 学习数据文件
        self.feedback_file = self.data_dir / "learning_feedback.jsonl"
        self.profile_file = self.data_dir / "speaker_profiles.json"
        self.thresholds_file = self.data_dir / "learned_thresholds.json"
        self.stats_file = self.data_dir / "learning_stats.json"
        self._restrict_permissions()
        
        # 当前阈值配置（会从文件加载或默认值）
        self.thresholds = self._load_thresholds()
        
        # 说话人画像
        self.speaker_profiles = self._load_profiles()
        
        # 统计数据
        self.stats = self._load_stats()

    @staticmethod
    def _private_opener(path, flags):
        return os.open(path, flags, 0o600)

    def _restrict_permissions(self):
        """Protect stored text feedback and derived profiles on the local device."""
        for path in (
            self.feedback_file,
            self.profile_file,
            self.thresholds_file,
            self.stats_file,
        ):
            if path.exists():
                os.chmod(path, 0o600)
        
    def _load_thresholds(self) -> dict:
        """加载学习到的阈值"""
        if self.thresholds_file.exists():
            with open(self.thresholds_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 默认阈值
        return {
            "emotion_score_min": 30,
            "violence_confidence_min": 0.5,
            "acoustic_risk_min": 30,
            "volume_rms_shouting": 2000,
            "pitch_jump_threshold": 6.0,
            "last_updated": None,
            "version": 1
        }
    
    def _load_profiles(self) -> dict:
        """加载说话人画像"""
        if self.profile_file.exists():
            with open(self.profile_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_stats(self) -> dict:
        """加载学习统计"""
        if self.stats_file.exists():
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "total_feedback": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "confirmed": 0,
            "accuracy_history": [],
            "last_analysis": None
        }
    
    def _save_thresholds(self):
        """保存阈值配置"""
        self.thresholds["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.thresholds_file, 'w', encoding='utf-8', opener=self._private_opener) as f:
            json.dump(self.thresholds, f, ensure_ascii=False, indent=2)
        os.chmod(self.thresholds_file, 0o600)
    
    def _save_profiles(self):
        """保存说话人画像"""
        with open(self.profile_file, 'w', encoding='utf-8', opener=self._private_opener) as f:
            json.dump(self.speaker_profiles, f, ensure_ascii=False, indent=2)
        os.chmod(self.profile_file, 0o600)
    
    def _save_stats(self):
        """保存统计数据"""
        with open(self.stats_file, 'w', encoding='utf-8', opener=self._private_opener) as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        os.chmod(self.stats_file, 0o600)
    
    def add_feedback(self, event_data: dict, feedback_type: str, 
                     user_note: str = "") -> dict:
        """添加用户反馈"""
        feedback = {
            "ts": event_data.get("ts"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "feedback_type": feedback_type,
            "text": event_data.get("text", ""),
            "original_result": {
                "is_violence": event_data.get("is_violence"),
                "violence_confidence": event_data.get("violence_confidence"),
                "violence_type": event_data.get("violence_type"),
                "emotion_type": event_data.get("emotion_type"),
                "emotion_score": event_data.get("emotion_score"),
                "acoustic_risk_score": event_data.get("acoustic_risk_score"),
            },
            "acoustic_features": {
                "volume_rms": event_data.get("volume_rms"),
                "volume_level": event_data.get("volume_level"),
                "pitch_f0": event_data.get("pitch_f0"),
                "pitch_trend": event_data.get("pitch_trend"),
                "pitch_jump": event_data.get("pitch_jump"),
            },
            "user_note": user_note,
            "speaker": event_data.get("speaker", "unknown"),
            "scene": event_data.get("scene", "家庭")
        }
        
        with open(self.feedback_file, 'a', encoding='utf-8', opener=self._private_opener) as f:
            f.write(json.dumps(feedback, ensure_ascii=False) + '\n')
        os.chmod(self.feedback_file, 0o600)
        
        self.stats["total_feedback"] += 1
        if feedback_type == "false_positive":
            self.stats["false_positives"] += 1
        elif feedback_type == "false_negative":
            self.stats["false_negatives"] += 1
        elif feedback_type == "confirmed":
            self.stats["confirmed"] += 1
        
        self._update_speaker_profile(event_data, feedback_type)
        self._save_stats()
        self._save_profiles()
        
        return {
            "ok": True,
            "feedback_id": feedback["ts"],
            "current_stats": {
                "total": self.stats["total_feedback"],
                "false_positives": self.stats["false_positives"],
                "false_negatives": self.stats["false_negatives"],
                "confirmed": self.stats["confirmed"],
                "accuracy": self._calculate_accuracy()
            }
        }
    
    def _update_speaker_profile(self, event_data: dict, feedback_type: str):
        """更新说话人画像"""
        speaker = event_data.get("speaker", "unknown")
        if speaker not in self.speaker_profiles:
            self.speaker_profiles[speaker] = {
                "feedback_count": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "avg_volume_rms": [],
                "avg_pitch_f0": [],
                "typical_emotion_scores": [],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        profile = self.speaker_profiles[speaker]
        profile["feedback_count"] += 1
        profile["last_feedback"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        if feedback_type == "false_positive":
            profile["false_positives"] += 1
        elif feedback_type == "false_negative":
            profile["false_negatives"] += 1
        
        if event_data.get("volume_rms"):
            profile["avg_volume_rms"].append(event_data["volume_rms"])
            profile["avg_volume_rms"] = profile["avg_volume_rms"][-100:]
        
        if event_data.get("pitch_f0") and event_data["pitch_f0"] > 0:
            profile["avg_pitch_f0"].append(event_data["pitch_f0"])
            profile["avg_pitch_f0"] = profile["avg_pitch_f0"][-100:]
        
        if event_data.get("emotion_score"):
            profile["typical_emotion_scores"].append(event_data["emotion_score"])
            profile["typical_emotion_scores"] = profile["typical_emotion_scores"][-100:]
    
    def _calculate_accuracy(self) -> float:
        """计算当前准确率"""
        total = self.stats["total_feedback"]
        if total == 0:
            return 1.0
        correct = self.stats["confirmed"]
        return round(correct / total, 3)
    
    def analyze_and_learn(self) -> dict:
        """分析反馈数据并学习优化"""
        if not self.feedback_file.exists():
            return {"ok": False, "error": "No feedback data yet"}
        
        feedbacks = []
        with open(self.feedback_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    feedbacks.append(json.loads(line.strip()))
                except:
                    continue
        
        if len(feedbacks) < 5:
            return {"ok": False, "error": "Need at least 5 feedback samples for analysis"}
        
        # 分析误报模式 (false_positive)
        fp_data = [f for f in feedbacks if f["feedback_type"] == "false_positive"]
        fn_data = [f for f in feedbacks if f["feedback_type"] == "false_negative"]
        
        analysis = {
            "false_positive_patterns": self._analyze_misclassifications(fp_data),
            "false_negative_patterns": self._analyze_misclassifications(fn_data),
            "suggested_adjustments": {}
        }
        
        # 生成阈值调整建议
        adjustments = self._generate_threshold_adjustments(fp_data, fn_data)
        analysis["suggested_adjustments"] = adjustments
        
        # 更新阈值
        if adjustments.get("apply", False):
            self._apply_threshold_adjustments(adjustments["changes"])
        
        self.stats["last_analysis"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.stats["accuracy_history"].append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy": self._calculate_accuracy()
        })
        self._save_stats()
        
        return {
            "ok": True,
            "analysis": analysis,
            "thresholds_applied": adjustments.get("apply", False),
            "current_thresholds": self.thresholds,
            "stats": self.stats
        }
    
    def _analyze_misclassifications(self, feedback_data: list) -> dict:
        """分析误分类模式"""
        if not feedback_data:
            return {}
        
        patterns = {
            "count": len(feedback_data),
            "common_emotions": Counter(),
            "common_violence_types": Counter(),
            "avg_emotion_score": 0,
            "avg_acoustic_risk": 0,
            "volume_levels": Counter(),
            "typical_confidence_range": {"min": 1.0, "max": 0.0}
        }
        
        emotion_scores = []
        acoustic_risks = []
        
        for fb in feedback_data:
            orig = fb.get("original_result", {})
            patterns["common_emotions"][orig.get("emotion_type", "unknown")] += 1
            patterns["common_violence_types"][orig.get("violence_type", "unknown")] += 1
            
            if orig.get("emotion_score"):
                emotion_scores.append(orig["emotion_score"])
            if orig.get("acoustic_risk_score"):
                acoustic_risks.append(orig["acoustic_risk_score"])
            
            conf = orig.get("violence_confidence", 0)
            patterns["typical_confidence_range"]["min"] = min(patterns["typical_confidence_range"]["min"], conf)
            patterns["typical_confidence_range"]["max"] = max(patterns["typical_confidence_range"]["max"], conf)
            
            acoustic = fb.get("acoustic_features", {})
            patterns["volume_levels"][acoustic.get("volume_level", "unknown")] += 1
        
        if emotion_scores:
            patterns["avg_emotion_score"] = round(statistics.mean(emotion_scores), 1)
        if acoustic_risks:
            patterns["avg_acoustic_risk"] = round(statistics.mean(acoustic_risks), 1)
        
        return patterns
    
    def _generate_threshold_adjustments(self, fp_data: list, fn_data: list) -> dict:
        """生成阈值调整建议"""
        changes = {}
        
        # 误报过多 -> 提高阈值
        if len(fp_data) > len(fn_data) * 2:
            changes["violence_confidence_min"] = self.thresholds["violence_confidence_min"] + 0.05
            changes["emotion_score_min"] = self.thresholds["emotion_score_min"] + 5
            changes["acoustic_risk_min"] = self.thresholds["acoustic_risk_min"] + 5
        
        # 漏报过多 -> 降低阈值
        elif len(fn_data) > len(fp_data) * 2:
            changes["violence_confidence_min"] = max(0.3, self.thresholds["violence_confidence_min"] - 0.05)
            changes["emotion_score_min"] = max(15, self.thresholds["emotion_score_min"] - 5)
            changes["acoustic_risk_min"] = max(15, self.thresholds["acoustic_risk_min"] - 5)
        
        # 分析具体特征调整音量阈值
        if fp_data:
            loud_fp = [f for f in fp_data if f.get("acoustic_features", {}).get("volume_level") in ["loud", "shouting"]]
            if len(loud_fp) > len(fp_data) * 0.5:
                changes["volume_rms_shouting"] = self.thresholds["volume_rms_shouting"] + 200
        
        result = {
            "apply": len(changes) > 0,
            "changes": changes,
            "reason": self._generate_adjustment_reason(fp_data, fn_data, changes)
        }
        return result
    
    def _generate_adjustment_reason(self, fp_data, fn_data, changes) -> str:
        """生成调整原因说明"""
        reasons = []
        if len(fp_data) > len(fn_data) * 2:
            reasons.append(f"误报({len(fp_data)})显著多于漏报({len(fn_data)})，提高阈值")
        elif len(fn_data) > len(fp_data) * 2:
            reasons.append(f"漏报({len(fn_data)})显著多于误报({len(fp_data)})，降低阈值")
        if "volume_rms_shouting" in changes:
            reasons.append("音量阈值调整以减少噪音误报")
        return "; ".join(reasons) if reasons else "维持当前阈值"
    
    def _apply_threshold_adjustments(self, changes: dict):
        """应用阈值调整"""
        for key, value in changes.items():
            self.thresholds[key] = round(value, 3) if isinstance(value, float) else value
        self._save_thresholds()
    
    def get_learning_report(self) -> dict:
        """获取学习报告"""
        return {
            "ok": True,
            "stats": self.stats,
            "thresholds": self.thresholds,
            "speaker_count": len(self.speaker_profiles),
            "top_speakers": sorted(
                [(s, p) for s, p in self.speaker_profiles.items()],
                key=lambda x: x[1].get("feedback_count", 0),
                reverse=True
            )[:5]
        }
    
    def get_speaker_profile(self, speaker: str) -> dict:
        """获取特定说话人的画像"""
        profile = self.speaker_profiles.get(speaker)
        if not profile:
            return {"ok": False, "error": "Speaker not found"}
        
        result = profile.copy()
        
        # 计算统计数据
        if profile.get("avg_volume_rms"):
            result["volume_rms_avg"] = round(statistics.mean(profile["avg_volume_rms"]), 1)
            result["volume_rms_std"] = round(statistics.stdev(profile["avg_volume_rms"]), 1) if len(profile["avg_volume_rms"]) > 1 else 0
        
        if profile.get("typical_emotion_scores"):
            result["emotion_score_avg"] = round(statistics.mean(profile["typical_emotion_scores"]), 1)
        
        return {"ok": True, "profile": result}

# 单例实例
_learning_engine = None

def get_learning_engine() -> LearningEngine:
    """获取学习引擎单例"""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine()
    return _learning_engine

if __name__ == "__main__":
    # 测试
    engine = LearningEngine()
    print("学习引擎初始化完成")
    print("当前阈值:", engine.thresholds)
    print("统计:", engine.stats)

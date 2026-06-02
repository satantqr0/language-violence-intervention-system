#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端侧语音识别混合语义分析语言暴力检测与主动干预系统
适配树莓派5 / Mac Mini M1/M2

核心模块：音频采集 → VAD → 媒体声过滤 → ASR → 声学分析(音量+语调) → 情绪分析 → 双引擎检测 → 场景适配 → 声纹识别 → TTS干预 → 日志记录
"""

import os
import sys
import time
import json
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from env_loader import load_env_file
from audio_capture import AudioCapture
from vad_engine import VADEngine
from media_guard import MediaGuard
from acoustic_analyzer import AcousticAnalyzer
from asr_engine import ASREngine
from ali_asr_engine import AliASREngine
from emotion_analyzer import EmotionAnalyzer
from semantic_analyzer import SemanticAnalyzer
from ali_llm_engine import AliLLMEngine
from scene_manager import SceneManager
from voiceprint import VoiceprintEngine
from tts_engine import TTSEngine
from ali_tts_engine import AliTTSEngine
from event_logger import EventLogger
from learning_engine import get_learning_engine

import numpy as np


load_env_file(PROJECT_ROOT / ".env")


class ViolenceDetectionSystem:
    """语言暴力检测与主动干预系统主类"""
    
    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.running = False
        data_dir = Path(os.getenv("VD_DATA_DIR") or PROJECT_ROOT / "data")
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        
        # 初始化各模块
        self.audio_capture = AudioCapture(
            sample_rate=self.config["audio"]["sample_rate"],
            chunk_duration=self.config["audio"]["chunk_duration"]
        )
        vad_cfg = self.config.get('vad', {})
        self.vad_engine = VADEngine(
            threshold=vad_cfg.get('threshold', 0.5),
            silence_duration=vad_cfg.get('silence_duration', 0.8),
            max_sentence_duration=self.config.get('max_sentence_duration', 5.0),
            audio_save_dir=self._resolve_audio_save_dir()
        )
        acoustic_cfg = self.config.get('acoustic', {})
        self.acoustic_analyzer = AcousticAnalyzer(
            sample_rate=self.config["audio"]["sample_rate"],
            volume_spike_ratio=acoustic_cfg.get('volume_spike_ratio', 2.5),
            pitch_jump_semitones=acoustic_cfg.get('pitch_jump_semitones', 6.0),
            baseline_window=acoustic_cfg.get('baseline_window', 30),
            min_pitch_hz=acoustic_cfg.get('min_pitch_hz', 60.0),
            max_pitch_hz=acoustic_cfg.get('max_pitch_hz', 500.0)
        )
        media_cfg = self.config.get("media_guard", {})
        self.media_guard = MediaGuard(
            data_dir=str(data_dir),
            sample_rate=self.config["audio"]["sample_rate"],
            enabled=media_cfg.get("enabled", True),
            mode=media_cfg.get("mode", "balanced"),
            match_margin=media_cfg.get("match_margin", 0.035),
            max_media_distance=media_cfg.get("max_media_distance", 0.17),
            shouting_bypass_rms=media_cfg.get("shouting_bypass_rms", 2500),
        )
        
        # 学习引擎：读取用户反馈形成的动态阈值
        self.learning_engine = None
        self.learning_enabled = self.config.get("learning", {}).get("enabled", True)
        if self.learning_enabled:
            try:
                self.learning_engine = get_learning_engine()
                print("   学习引擎已启用 (动态阈值)")
            except Exception as e:
                print(f"   学习引擎不可用，使用固定阈值: {e}")

        # ASR 引擎选择
        asr_engine_type = self.config["asr"].get("engine", "local_whisper")
        has_key = bool(self.config.get("api", {}).get("dashscope_api_key"))
        if asr_engine_type in ("fun_asr", "ali_asr") and has_key:
            self.asr_engine = AliASREngine(
                api_key=self.config["api"]["dashscope_api_key"],
                model=self.config["asr"].get("fun_asr", {}).get("model", "paraformer-realtime-v2"),
                language_hints=self.config["asr"].get("language_hints", [])
            )
            self._use_ali_asr = True
            print(f"   使用阿里云 ASR 引擎 (方言: {self.config['asr'].get('language_hints', [])})")
        else:
            self.asr_engine = ASREngine(model_size=self.config["asr"]["model_size"])
            self._use_ali_asr = False
            print(f"   使用本地 Whisper 引擎")
        
        # LLM 引擎：情绪分析与语义分析按文档使用不同模型
        if self.config.get("api", {}).get("dashscope_api_key"):
            api_cfg = self.config["api"]
            self.semantic_llm_engine = AliLLMEngine(
                api_key=self.config["api"]["dashscope_api_key"],
                model=api_cfg.get("semantic_llm", {}).get("model", "qwen-plus")
            )
            self.emotion_llm_engine = AliLLMEngine(
                api_key=self.config["api"]["dashscope_api_key"],
                model=api_cfg.get("emotion_llm", {}).get("model", "qwen-turbo")
            )
        else:
            self.semantic_llm_engine = None
            self.emotion_llm_engine = None
        
        self.emotion_analyzer = EmotionAnalyzer(llm_engine=self.emotion_llm_engine)
        self.semantic_analyzer = SemanticAnalyzer(
            rules_path=PROJECT_ROOT / "config" / "violence_rules.json",
            llm_engine=self.semantic_llm_engine
        )
        self.scene_manager = SceneManager(
            default_scene=self.config["scene"]["default"]
        )
        voiceprint_cfg = self.config.get("voiceprint", {})
        self.voiceprint_engine = VoiceprintEngine(
            data_dir=str(data_dir),
            model_dir=str(PROJECT_ROOT / "models" / "spkrec-ecapa-voxceleb"),
            match_threshold=voiceprint_cfg.get("match_threshold", 0.45),
            max_speakers=voiceprint_cfg.get("max_speakers", 8),
            max_templates_per_speaker=voiceprint_cfg.get("max_templates_per_speaker", 3),
        )
        
        tts_engine_type = self.config["tts"].get("engine", "edge_tts")
        if tts_engine_type in ("sambert", "cosyvoice", "ali_tts") and self.config.get("api", {}).get("dashscope_api_key"):
            self.tts_engine = AliTTSEngine(
                api_key=self.config["api"]["dashscope_api_key"],
                model=self.config["api"]["tts"].get("model", "sambert-zhichu-v1"),
                voice=self.config["api"]["tts"].get("voice", self.config["tts"].get("voice", "zhichu"))
            )
        else:
            self.tts_engine = TTSEngine(
                voice=self.config["tts"].get("voice", "zh-CN-XiaoxiaoNeural")
            )
        self.event_logger = EventLogger(log_dir=PROJECT_ROOT / "logs")
        
        # 上下文缓存
        self.context_history: List[Dict] = []
        self.max_context_length = 10
        
        # 流式 ASR 状态
        self._asr_stream_active = False
    
    def _load_config(self, config_path: str = None) -> Dict:
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self._apply_env_overrides(config)
        return config
    
    def _apply_env_overrides(self, config: Dict):
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if dashscope_key:
            api_config = config.setdefault("api", {})
            api_config["dashscope_api_key"] = dashscope_key
            for key in ("semantic_llm", "emotion_llm"):
                if isinstance(api_config.get(key), dict):
                    api_config[key]["api_key"] = dashscope_key
        save_recordings = os.getenv("VD_SAVE_RECORDINGS", "").strip().lower()
        if save_recordings:
            config.setdefault("audio", {})["save_recordings"] = save_recordings in ("1", "true", "yes", "on")
    
    def _resolve_audio_save_dir(self) -> Optional[str]:
        audio_cfg = self.config.get("audio", {})
        if audio_cfg.get("save_recordings", True) is False:
            return ""
        save_dir = os.getenv("VD_AUDIO_DIR") or audio_cfg.get("save_dir")
        if not save_dir:
            return str(PROJECT_ROOT / "audio")
        path = Path(save_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)
    
    def start(self):
        print("=" * 50)
        print("语言暴力检测与主动干预系统启动中...")
        print("=" * 50)
        
        print("[1/10] 初始化音频采集模块...")
        self.audio_capture.start()
        print("[2/10] 初始化VAD人声检测...")
        self.vad_engine.load()
        print("[3/10] 初始化媒体声过滤...")
        self.media_guard.load()
        print("[4/10] 初始化声学特征分析(音量+语调)...")
        self.acoustic_analyzer.load()
        print("[5/10] 加载ASR模型...")
        self.asr_engine.load()
        print("[6/10] 初始化情绪分析模块...")
        self.emotion_analyzer.load()
        print("[7/10] 加载语义分析规则引擎...")
        self.semantic_analyzer.load()
        print("[8/10] 初始化场景管理器...")
        self.scene_manager.load()
        print("[9/10] 初始化声纹识别模块...")
        self.voiceprint_engine.load()
        print("[10/10] 初始化TTS干预模块...")
        self.tts_engine.load()
        
        self.running = True
        media_status = self.media_guard.status()
        if self._use_ali_asr and media_status["enabled"] and media_status["ready"]:
            asr_mode = "云端分段(本地媒体过滤后上传)"
        elif self._use_ali_asr:
            asr_mode = "流式(完成媒体校准后启用前置过滤)"
        else:
            asr_mode = "离线(Whisper)"
        print(f"\n✅ 系统启动完成!")
        print(f"   当前场景: {self.scene_manager.current_scene}")
        print(f"   灵敏度: {self.scene_manager.get_sensitivity()}")
        print(f"   ASR模式: {asr_mode}")
        print(f"   媒体声过滤: {'已就绪' if media_status['ready'] else '待校准'}")
        print(f"   声学检测: 音量突变(>{self.acoustic_analyzer.volume_spike_ratio}x) + 语调突变(>{self.acoustic_analyzer.pitch_jump_semitones}半音)")
        print("\n按 Ctrl+C 停止系统\n")
        self._main_loop()
    
    def _main_loop(self):
        try:
            while self.running:
                try:
                    self._process_one_cycle()
                except Exception as e:
                    print(f"[主循环异常] {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    self._cleanup_asr_stream()
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def _cleanup_asr_stream(self):
        if self._asr_stream_active and self._use_ali_asr:
            try:
                self.asr_engine.end_stream(timeout=1.0)
            except:
                pass
        self._asr_stream_active = False
    
    def _process_one_cycle(self):
        """单次处理周期
        
        ASR 核心时序：
        1. 读入音频帧
        2. VAD 完成一句声音缓冲
        3. 在任何 ASR/云端调用前过滤高置信媒体声
        4. 仅对放行的声音执行 ASR 和风险分析
        """
        audio_chunk = self.audio_capture.read()
        if audio_chunk is None:
            time.sleep(0.01)
            return
        
        if self._use_ali_asr:
            self._process_streaming(audio_chunk)
        else:
            self._process_batch(audio_chunk)
    
    def _process_streaming(self, audio_chunk: np.ndarray):
        """Cloud ASR mode buffered through the local media gate before upload."""
        media_status = self.media_guard.status()
        if not media_status["enabled"] or not media_status["ready"]:
            self._process_direct_streaming(audio_chunk)
            return
        sentence_audio = self.vad_engine.process_audio(audio_chunk)
        if sentence_audio is None:
            return

        if self._suppress_media_audio(sentence_audio):
            return
        try:
            acoustic_result = self.acoustic_analyzer.analyze(sentence_audio)
        except Exception as e:
            print(f"[声学分析异常] {e}")
            acoustic_result = self._default_acoustic_result()
        
        self._print_acoustic_info(acoustic_result)
        
        try:
            text = self.asr_engine.transcribe(sentence_audio)
        except Exception as e:
            print(f"[ASR异常] {e}")
            text = None
        
        self._process_text(text, acoustic_result, sentence_audio)

    def _process_direct_streaming(self, audio_chunk: np.ndarray):
        """Preserve low-latency ASR until the media gate has both calibrations."""
        if self._asr_stream_active:
            try:
                self.asr_engine.send_audio(audio_chunk)
            except Exception as e:
                print(f"[ASR流式发送异常] {e}")
                self._cleanup_asr_stream()
        sentence_audio = self.vad_engine.process_audio(audio_chunk)
        if sentence_audio is None:
            if self.vad_engine.is_speaking and not self._asr_stream_active:
                try:
                    self.asr_engine.start_stream()
                    self._asr_stream_active = True
                    self.asr_engine.send_audio(audio_chunk)
                    print("[ASR流式] 会话开始（媒体过滤待校准）")
                except Exception as e:
                    print(f"[ASR流式启动异常] {e}")
                    self._asr_stream_active = False
            return
        try:
            acoustic_result = self.acoustic_analyzer.analyze(sentence_audio)
        except Exception as e:
            print(f"[声学分析异常] {e}")
            acoustic_result = self._default_acoustic_result()
        self._print_acoustic_info(acoustic_result)
        if self._asr_stream_active:
            try:
                text = self.asr_engine.end_stream(timeout=8.0)
            except Exception as e:
                print(f"[ASR流式结束异常] {e}")
                text = None
            self._asr_stream_active = False
        else:
            try:
                text = self.asr_engine.transcribe(sentence_audio)
            except Exception as e:
                print(f"[ASR异常] {e}")
                text = None
        self._process_text(text, acoustic_result, sentence_audio)
    
    def _process_batch(self, audio_chunk: np.ndarray):
        """非流式模式（Whisper）"""
        sentence_audio = self.vad_engine.process_audio(audio_chunk)
        if sentence_audio is None:
            return

        if self._suppress_media_audio(sentence_audio):
            return
        
        try:
            acoustic_result = self.acoustic_analyzer.analyze(sentence_audio)
        except Exception as e:
            print(f"[声学分析异常] {e}")
            acoustic_result = self._default_acoustic_result()
        
        self._print_acoustic_info(acoustic_result)
        
        try:
            text = self.asr_engine.transcribe(sentence_audio)
        except Exception as e:
            print(f"[ASR异常] {e}")
            return
        
        self._process_text(text, acoustic_result, sentence_audio)

    def _suppress_media_audio(self, sentence_audio: np.ndarray) -> bool:
        """Drop only high-confidence playback matches before costly transcription."""
        try:
            decision = self.media_guard.classify(sentence_audio)
            if decision.get("suppressed"):
                self.media_guard.record_suppression(decision)
                print(
                    "[媒体声过滤] 已跳过疑似电视/歌曲声音 "
                    f"(媒体距离={decision.get('media_distance', '-')}, "
                    f"真人距离={decision.get('human_distance', '-')})"
                )
                return True
        except Exception as e:
            print(f"[媒体声过滤异常] {e}")
        return False
    
    def _process_text(self, text: str, acoustic_result: Dict, sentence_audio: np.ndarray):
        """处理识别出的文本"""
        vol = acoustic_result["volume"]
        pit = acoustic_result["pitch"]
        risk = acoustic_result["acoustic_risk"]
        
        if not text or len(text.strip()) < 2:
            if risk["is_high_risk"]:
                print(f"[声学预警] ASR无文本但声学风险极高({risk['score']}): {'; '.join(risk['factors'])}")
            else:
                audio_dur = len(sentence_audio) / self.audio_capture.sample_rate if hasattr(self, 'audio_capture') else 0
                print(f"[ASR] 无有效文本 (text={repr(text)})")
            return
        
        print(f"\n[检测到语音] {text}")
        
        # 情绪分析
        try:
            emotion_result = self.emotion_analyzer.analyze(text, context=self.context_history)
        except Exception as e:
            print(f"[情绪分析异常] {e}")
            emotion_result = {"type": "未知", "intensity": "low", "score": 0, "is_high_risk": False}
        
        # 语义暴力检测
        try:
            violence_result = self.semantic_analyzer.analyze(
                text=text,
                emotion_intensity=emotion_result.get("intensity", "low"),
                context=self.context_history
            )
        except Exception as e:
            print(f"[语义分析异常] {e}")
            violence_result = {"is_violence": False, "type": "无", "confidence": 0, "severity": "none"}
        
        # 声纹识别
        try:
            voice_match = self.voiceprint_engine.identify_with_score(sentence_audio)
            speaker = voice_match["speaker_id"]
            if voice_match.get("matched"):
                print(f"[声纹识别] {speaker} (相似度 {voice_match['score']:.3f})")
        except Exception as exc:
            print(f"[声纹识别异常] {exc}")
            voice_match = {
                "speaker_id": "unknown",
                "matched": False,
                "score": 0.0,
                "source": "voiceprint",
            }
            speaker = "unknown"
        
        # 声学特征融入暴力检测
        acoustic_trigger_min = self._learned_threshold("acoustic_risk_min", 80)
        if risk["is_high_risk"] and violence_result.get("is_violence", False):
            boost = min(0.3, risk["score"] / 100 * 0.4)
            violence_result["confidence"] = min(1.0, violence_result.get("confidence", 0) + boost)
            violence_result["acoustic_confirmed"] = True
            print(f"[声学确认] 暴力置信度提升 +{boost:.2f} → {violence_result['confidence']:.2f}")
        elif risk["is_high_risk"] and not violence_result.get("is_violence", False):
            violence_result["acoustic_suspect"] = True
            violence_result["acoustic_factors"] = risk["factors"]
            if risk["score"] >= acoustic_trigger_min:
                violence_result["is_violence"] = True
                violence_result["type"] = "声学异常"
                violence_result["confidence"] = risk["score"] / 100 * 0.7
                violence_result["severity"] = "medium"
                violence_result["learning_acoustic_trigger_min"] = acoustic_trigger_min
                print(f"[声学触发] 纯声学暴力检测触发(阈值{acoustic_trigger_min}): {'; '.join(risk['factors'])}")
        
        # 更新上下文
        self._update_context(text, emotion_result, violence_result, speaker, acoustic_result, voice_match)
        
        # 场景检测
        try:
            new_scene = self.scene_manager.detect_scene(text)
            if new_scene and new_scene != self.scene_manager.current_scene:
                print(f"[场景切换] {self.scene_manager.current_scene} → {new_scene}")
                self.scene_manager.switch_scene(new_scene)
        except Exception as e:
            print(f"[场景切换异常] {e}")
        
        # 判断干预
        should_intervene = self._should_intervene(
            violence_result, emotion_result,
            self.scene_manager.get_sensitivity(), acoustic_result
        )
        intervention_text = None
        if should_intervene:
            try:
                intervention_text = self._trigger_intervention(violence_result, acoustic_result)
            except Exception as e:
                print(f"[干预异常] {e}")
        
        # 记录事件
        try:
            self._log_event(text, emotion_result, violence_result, speaker, acoustic_result, intervention_text, voice_match)
        except Exception as e:
            print(f"[日志异常] {e}")
    
    def _print_acoustic_info(self, acoustic_result: Dict):
        vol = acoustic_result["volume"]
        pit = acoustic_result["pitch"]
        risk = acoustic_result["acoustic_risk"]
        
        acoustic_tag = ""
        if risk["is_high_risk"]:
            acoustic_tag = " 🔊声学高风险"
        if vol["is_spike"]:
            acoustic_tag += f" ⚡音量突变{vol['spike_ratio']:.1f}x"
        if pit["is_jump"]:
            direction = "↑" if pit["jump_semitones"] > 0 else "↓"
            acoustic_tag += f" 🎵语调突变{direction}{abs(pit['jump_semitones']):.0f}半音"
        
        print(f"[声学] 音量={vol['level']}(RMS={vol['rms']:.0f}) 基频={pit['f0']:.0f}Hz 语调={pit['trend']} 声学风险={risk['score']}{acoustic_tag}")
    
    def _default_acoustic_result(self) -> Dict:
        return {
            "volume": {"rms": 0, "baseline_rms": 0, "spike_ratio": 1.0, "is_spike": False, "level": "quiet"},
            "pitch": {"f0": 0, "baseline_f0": 0, "jump_semitones": 0, "is_jump": False, "trend": "stable"},
            "acoustic_risk": {"score": 0, "factors": [], "is_high_risk": False}
        }
    
    def _update_context(self, text: str, emotion: Dict, violence: Dict, speaker: str, acoustic: Dict = None,
                        voice_match: Dict = None):
        entry = {
            "text": text,
            "emotion": emotion,
            "violence": violence,
            "speaker": speaker,
            "timestamp": time.time()
        }
        if acoustic:
            entry["acoustic"] = {
                "volume_level": acoustic["volume"]["level"],
                "volume_spike": bool(acoustic["volume"]["is_spike"]),
                "pitch_f0": acoustic["pitch"]["f0"],
                "pitch_trend": acoustic["pitch"]["trend"],
                "acoustic_risk_score": acoustic["acoustic_risk"]["score"]
            }
        if voice_match:
            entry["voiceprint"] = {
                "matched": bool(voice_match.get("matched")),
                "score": voice_match.get("score", 0),
                "threshold": voice_match.get("threshold"),
            }
        self.context_history.append(entry)
        if len(self.context_history) > self.max_context_length:
            self.context_history.pop(0)

    def _learned_threshold(self, key: str, default):
        if not self.learning_engine:
            return default
        try:
            return self.learning_engine.thresholds.get(key, default)
        except Exception:
            return default
    
    def _should_intervene(self, violence_result: Dict, emotion_result: Dict, 
                          sensitivity: float, acoustic_result: Dict = None) -> bool:
        if not violence_result.get("is_violence", False):
            return False
        confidence = violence_result.get("confidence", 0)
        severity = violence_result.get("severity", "low")
        severity_thresholds = {"high": 0.5, "medium": 0.7, "low": 0.85}
        threshold = severity_thresholds.get(severity, 0.8)
        learned_min = self._learned_threshold("violence_confidence_min", None)
        if learned_min is not None:
            scale = max(0.6, min(1.4, float(learned_min) / 0.5))
            threshold = max(0.3, min(0.95, threshold * scale))
        adjusted_threshold = threshold * sensitivity
        if acoustic_result and acoustic_result["acoustic_risk"]["is_high_risk"]:
            adjusted_threshold *= 0.75
            print(f"[声学加权] 干预阈值降低25%: {threshold * sensitivity:.2f} → {adjusted_threshold:.2f}")
        violence_result["intervention_threshold"] = round(adjusted_threshold, 3)
        return confidence >= adjusted_threshold
    
    def _trigger_intervention(self, violence_result: Dict, acoustic_result: Dict = None):
        severity = violence_result.get("severity", "low")
        intervention_text = self.tts_engine.get_intervention_text(severity)
        acoustic_info = ""
        if acoustic_result and acoustic_result["acoustic_risk"]["is_high_risk"]:
            factors = acoustic_result["acoustic_risk"]["factors"]
            acoustic_info = f" | 声学因素: {'; '.join(factors)}"
        print(f"\n🚨 [干预触发] 严重度: {severity}{acoustic_info}")
        print(f"   干预内容: {intervention_text}")
        self.tts_engine.speak(intervention_text)
        return intervention_text
    
    def _log_event(self, text: str, emotion: Dict, violence: Dict, speaker: str, acoustic: Dict = None,
                   intervention_text: str = None, voice_match: Dict = None):
        event_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
            "text": text,
            "emotion_type": emotion.get("type", "unknown"),
            "emotion_intensity": emotion.get("intensity", "unknown"),
            "emotion_score": emotion.get("score", 0),
            "violence_type": violence.get("type"),
            "violence_confidence": violence.get("confidence", 0),
            "violence_severity": violence.get("severity", "unknown"),
            "is_violence": violence.get("is_violence", False),
            "speaker": speaker,
            "speaker_verified": bool(voice_match and voice_match.get("matched")),
            "speaker_match_source": voice_match.get("source", "") if voice_match and voice_match.get("matched") else "",
            "speaker_match_score": voice_match.get("score", 0) if voice_match else 0,
            "speaker_match_threshold": voice_match.get("threshold") if voice_match else None,
            "scene": self.scene_manager.current_scene,
            "intervention_text": intervention_text or "",
            "intervention_triggered": bool(intervention_text),
            "intervention_threshold": violence.get("intervention_threshold"),
            "analysis_reason": violence.get("reason", "")
        }
        if acoustic:
            event_data["volume_level"] = acoustic["volume"]["level"]
            event_data["volume_rms"] = acoustic["volume"]["rms"]
            event_data["volume_spike"] = bool(acoustic["volume"]["is_spike"])
            event_data["volume_spike_ratio"] = acoustic["volume"]["spike_ratio"]
            event_data["pitch_f0"] = acoustic["pitch"]["f0"]
            event_data["pitch_trend"] = acoustic["pitch"]["trend"]
            event_data["pitch_jump"] = bool(acoustic["pitch"]["is_jump"])
            event_data["acoustic_risk_score"] = acoustic["acoustic_risk"]["score"]
            event_data["acoustic_risk_factors"] = acoustic["acoustic_risk"]["factors"]
        self.event_logger.log(event_data)
    
    def stop(self):
        print("\n\n正在停止系统...")
        self.running = False
        self._cleanup_asr_stream()
        self.audio_capture.stop()
        self.event_logger.close()
        print("✅ 系统已停止")


def main():
    system = ViolenceDetectionSystem()
    try:
        system.start()
    except KeyboardInterrupt:
        system.stop()
    except Exception as e:
        print(f"系统致命错误: {e}")
        import traceback
        traceback.print_exc()
        system.stop()


if __name__ == "__main__":
    main()

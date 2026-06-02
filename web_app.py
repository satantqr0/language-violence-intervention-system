#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask Web 管理界面 - 语言暴力检测系统
"""

import os
import sys
import json
import hmac
import shutil
import socket
import ssl
import subprocess
import threading
import urllib.request
from pathlib import Path
import time
from datetime import datetime, timedelta
from flask import Flask, Response, render_template, jsonify, request
import numpy as np

# 导入学习引擎
sys.path.insert(0, str(Path(__file__).parent / "src"))
from speaker_profile_engine import SpeakerProfileEngine
from mental_screening_engine import MentalScreeningEngine, ScreeningError
from safety_case_engine import SafetyCaseEngine, SafetyCaseError
from media_guard import MediaGuard, MediaGuardError
from voiceprint import VoiceprintEngine, VoiceprintError
from display_localizer import display_value
try:
    from env_loader import load_env_file
    load_env_file(Path(__file__).parent / ".env")
    from learning_engine import get_learning_engine
    learning_engine = get_learning_engine()
    LEARNING_ENABLED = True
except Exception as e:
    print(f"学习引擎加载失败: {e}")
    learning_engine = None
    LEARNING_ENABLED = False

app = Flask(__name__)

# 日志目录
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

PROJECT_ROOT = Path(__file__).parent
LOGS_DIR = PROJECT_ROOT / "logs"
EVENTS_FILE = LOGS_DIR / "events.jsonl"
CONFIG_FILE = PROJECT_ROOT / "config" / "config.json"
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
_voiceprint_engine_cache = None
_voiceprint_engine_key = None
_voiceprint_capture_lock = threading.Lock()
_mental_screening_lock = threading.Lock()
_safety_case_lock = threading.Lock()

SAVED_KEY_MARKERS = {"___cached___", "___use_cached___"}
ASR_MODEL_OPTIONS = [
    {"id": "paraformer-realtime-v2", "label": "Paraformer 实时 v2（推荐，多语种/方言）"},
    {"id": "paraformer-realtime-v1", "label": "Paraformer 实时 v1（兼容模式）"},
]
EDGE_TTS_VOICE_OPTIONS = [
    {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓（自然女声）"},
    {"id": "zh-CN-XiaoyiNeural", "label": "晓伊（亲和女声）"},
    {"id": "zh-CN-YunxiNeural", "label": "云希（自然男声）"},
    {"id": "zh-CN-YunjianNeural", "label": "云健（稳重男声）"},
    {"id": "zh-CN-YunyangNeural", "label": "云扬（播音男声）"},
]
SAMBERT_VOICE_OPTIONS = [
    {"id": "sambert-zhiqi-v1", "label": "知琪（温柔女声）"},
    {"id": "sambert-zhichu-v1", "label": "知厨（舌尖男声）"},
    {"id": "sambert-zhide-v1", "label": "知德（新闻男声）"},
    {"id": "sambert-zhijia-v1", "label": "知佳（标准女声）"},
    {"id": "sambert-zhiru-v1", "label": "知茹（新闻女声）"},
    {"id": "sambert-zhixiang-v1", "label": "知祥（磁性男声）"},
    {"id": "sambert-zhijing-v1", "label": "知婧（严厉女声）"},
    {"id": "sambert-zhimo-v1", "label": "知墨（情感男声）"},
    {"id": "sambert-zhiyuan-v1", "label": "知媛（知心姐姐）"},
    {"id": "sambert-zhiyue-v1", "label": "知悦（温柔女声）"},
    {"id": "sambert-zhishuo-v1", "label": "知硕（自然男声）"},
    {"id": "sambert-zhimiao-emo-v1", "label": "知妙（多情感女声）"},
]

# 读取配置
def load_stored_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_config():
    config = load_stored_config()
    apply_env_overrides(config)
    return config

def apply_env_overrides(config):
    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    api_config = config.setdefault("api", {})
    # 环境变量优先，否则用 config 中已保存的 key
    if dashscope_key:
        api_config["dashscope_api_key"] = dashscope_key
    # 将 dashscope_api_key 同步到语义/情绪 LLM 子配置
    effective_key = api_config.get("dashscope_api_key", "")
    if effective_key:
        for key in ("semantic_llm", "emotion_llm"):
            sub = api_config.setdefault(key, {})
            if isinstance(sub, dict):
                # 仅当子配置的 api_key 为空时才填充
                if not sub.get("api_key"):
                    sub["api_key"] = effective_key

def update_env_value(name, value):
    """Write a runtime secret/config value without persisting it in JSON."""
    if "\n" in value or "\r" in value:
        raise ValueError("环境变量值不能包含换行")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    assignment = f"{name}={value}"
    updated = []
    replaced = False
    for line in lines:
        if line.startswith(f"{name}="):
            updated.append(assignment)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(assignment)
    ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)
    os.environ[name] = value

def persist_config(config):
    """Persist non-secret settings only; runtime secrets live in .env."""
    safe = json.loads(json.dumps(config, ensure_ascii=False))
    api_config = safe.setdefault("api", {})
    api_config["dashscope_api_key"] = ""
    for key in ("semantic_llm", "emotion_llm"):
        val = api_config.get(key)
        if isinstance(val, dict):
            val["api_key"] = ""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)

def redacted_config(config):
    safe = json.loads(json.dumps(config, ensure_ascii=False))
    api_config = safe.get("api", {})
    if api_config.get("dashscope_api_key"):
        api_config["dashscope_api_key"] = "***"
    for key in ("semantic_llm", "emotion_llm"):
        val = api_config.get(key)
        if isinstance(val, dict) and val.get("api_key"):
            val["api_key"] = "***"
    return safe

def models_url_for_openai_compatible(endpoint):
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"

def effective_dashscope_key(candidate=""):
    """Resolve a submitted key without ever treating UI cache markers as credentials."""
    candidate = (candidate or "").strip()
    if candidate and candidate not in SAVED_KEY_MARKERS:
        return candidate
    return load_config().get("api", {}).get("dashscope_api_key", "")

def fetch_dashscope_compatible_models(api_key):
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m["id"] for m in data.get("data", []) if m.get("id")]

def auth_error(message, status):
    if request.path.startswith("/api/"):
        response = jsonify({"ok": False, "error": message})
        response.status_code = status
    else:
        response = Response(message, status=status, mimetype="text/plain")
    if status == 401:
        response.headers["WWW-Authenticate"] = 'Basic realm="Family Violence Console", charset="UTF-8"'
    response.headers["Cache-Control"] = "no-store"
    return response

@app.before_request
def protect_console():
    """Require console credentials and reject cross-site state changes."""
    username = os.getenv("VD_WEB_USERNAME", "").strip()
    password = os.getenv("VD_WEB_PASSWORD", "").strip()
    if not username or not password:
        return auth_error("Web 管理端尚未配置登录凭据", 503)

    auth = request.authorization
    if not auth or not (
        hmac.compare_digest(auth.username or "", username)
        and hmac.compare_digest(auth.password or "", password)
    ):
        return auth_error("需要登录 Web 管理端", 401)

    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("X-Requested-With") != "FamilyViolenceConsole":
            return auth_error("请求校验失败", 403)

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

# 检查主检测服务是否在运行
def is_main_running():
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "language-violence-intervention-system.service"],
            capture_output=True
        )
        if result.returncode == 0:
            return True
        # 兼容旧版本：如果曾经由 Web 页面直接拉起主进程，也显示为运行中。
        legacy = subprocess.run(["pgrep", "-f", "src/main.py"], capture_output=True)
        return legacy.returncode == 0
    except Exception:
        return False

# 获取检测事件（高效尾部读取）
def get_recent_events(limit=20):
    events = []
    if not EVENTS_FILE.exists():
        return events
    try:
        file_size = EVENTS_FILE.stat().st_size
        if file_size == 0:
            return events
        # 大文件按请求条数分块回溯，避免固定字节窗口截断统计口径。
        if file_size > 512 * 1024:  # > 512KB
            with open(EVENTS_FILE, "rb") as f:
                chunks = []
                position = file_size
                newline_count = 0
                while position > 0 and newline_count <= limit:
                    read_size = min(position, 256 * 1024)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    chunks.append(chunk)
                    newline_count += chunk.count(b"\n")
                raw = b"".join(reversed(chunks)).decode("utf-8", errors="ignore")
                lines = raw.splitlines()
                # 未读取至文件开头时，首行可能是不完整的 JSON。
                if position > 0 and lines:
                    lines = lines[1:]
        else:
            lines = EVENTS_FILE.read_text(encoding="utf-8").strip().split("\n")
        for line in lines[-limit:]:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return events

def get_all_events():
    """Read complete event history for reports and profile aggregation."""
    events = []
    if not EVENTS_FILE.exists():
        return events
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as event_file:
            for line in event_file:
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return events

def effective_data_dir():
    path = Path(os.getenv("VD_DATA_DIR") or DATA_DIR)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path

def build_speaker_profile_engine():
    return SpeakerProfileEngine(log_dir=str(LOGS_DIR), data_dir=str(effective_data_dir()))

def build_mental_screening_engine():
    return MentalScreeningEngine(data_dir=str(effective_data_dir()))

def build_safety_case_engine():
    return SafetyCaseEngine(data_dir=str(effective_data_dir()))

def build_media_guard_engine():
    config = load_config().get("media_guard", {})
    return MediaGuard(
        data_dir=str(effective_data_dir()),
        sample_rate=load_config().get("audio", {}).get("sample_rate", 16000),
        enabled=config.get("enabled", True),
        mode=config.get("mode", "balanced"),
        match_margin=config.get("match_margin", 0.035),
        max_media_distance=config.get("max_media_distance", 0.17),
        shouting_bypass_rms=config.get("shouting_bypass_rms", 2500),
    )

def complete_speaker_profile(speaker_id, events, learning_profile=None):
    profile = build_speaker_profile_engine().build_profile(speaker_id, events, learning_profile)
    profile["screenings"] = build_mental_screening_engine().summary(speaker_id)
    return profile

def build_voiceprint_engine(load_model=False):
    """Share local template state in this Web worker without exposing embeddings."""
    global _voiceprint_engine_cache, _voiceprint_engine_key
    config = load_config().get("voiceprint", {})
    key = (
        str(effective_data_dir()),
        float(config.get("match_threshold", 0.45)),
        int(config.get("max_speakers", 8)),
        int(config.get("max_templates_per_speaker", 3)),
    )
    if _voiceprint_engine_cache is None or _voiceprint_engine_key != key:
        _voiceprint_engine_cache = VoiceprintEngine(
            data_dir=key[0],
            model_dir=str(PROJECT_ROOT / "models" / "spkrec-ecapa-voxceleb"),
            match_threshold=key[1],
            max_speakers=key[2],
            max_templates_per_speaker=key[3],
        )
        _voiceprint_engine_key = key
    else:
        _voiceprint_engine_cache.refresh_templates()
    if load_model and not _voiceprint_engine_cache.prepare():
        raise VoiceprintError(
            "声纹模型加载失败，请检查树莓派网络与模型依赖: "
            + (_voiceprint_engine_cache.load_error or "未知错误")
        )
    return _voiceprint_engine_cache

def control_detector_service(action):
    result = subprocess.run(
        ["sudo", "-n", "systemctl", action, "language-violence-intervention-system.service"],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        raise VoiceprintError(result.stderr.strip() or result.stdout.strip() or f"无法{action}检测服务")

def capture_voiceprint_audio(duration_seconds, process_audio=None):
    """Capture exclusively and process audio before the detector resumes."""
    from audio_capture import AudioCapture

    detector_was_running = is_main_running()
    capture = None
    chunks = []
    try:
        if detector_was_running:
            control_detector_service("stop")
            time.sleep(0.5)
        capture = AudioCapture(sample_rate=VoiceprintEngine.SAMPLE_RATE, chunk_duration=0.25)
        capture.start()
        deadline = time.monotonic() + duration_seconds
        while time.monotonic() < deadline:
            chunk = capture.read()
            if chunk is not None and len(chunk):
                chunks.append(chunk)
            time.sleep(0.03)
        tail = capture.read_all()
        if tail is not None and len(tail):
            chunks.append(tail)
        if not chunks:
            raise VoiceprintError("没有采集到声音，请检查麦克风输入")
        audio = np.concatenate(chunks).astype(np.int16, copy=False)
        capture.stop()
        capture = None
        return process_audio(audio) if process_audio else audio
    finally:
        if capture:
            capture.stop()
        if detector_was_running:
            control_detector_service("start")

def current_learning_profiles():
    if LEARNING_ENABLED and learning_engine:
        return learning_engine.speaker_profiles
    return {}

@app.route("/")
def index():
    """主页"""
    return render_template("index.html")

@app.route("/api/status")
def status():
    """系统状态"""
    config = load_config()
    running = is_main_running()
    
    # 读取统计
    stats = {"total": 0, "violence": 0}
    events = get_recent_events(1000)
    stats["total"] = len(events)
    stats["violence"] = sum(1 for e in events if e.get("is_violence", False))
    
    # LLM API 配置（隐藏密钥）
    api_config = config.get("api", {})
    llm_display = {}
    for key in ["semantic_llm", "emotion_llm"]:
        val = api_config.get(key)
        if val:
            llm_display[key] = {
                "provider": val.get("provider", ""),
                "model": val.get("model", ""),
                "endpoint": val.get("endpoint", ""),
                "has_key": bool(val.get("api_key"))
            }
        else:
            llm_display[key] = {"provider": "", "model": "", "endpoint": "", "has_key": False}
    
    has_dashscope_key = bool(config.get("api", {}).get("dashscope_api_key"))
    configured_asr = config.get("asr", {}).get("engine", "local_whisper")
    configured_tts = config.get("tts", {}).get("engine", "edge_tts")
    effective_asr = configured_asr if has_dashscope_key or configured_asr == "local_whisper" else "local_whisper"
    effective_tts = configured_tts if has_dashscope_key or configured_tts == "edge_tts" else "edge_tts"
    media_guard = build_media_guard_engine().status()

    return jsonify({
        "running": running,
        "scene": config.get("scene", {}).get("default", "家庭"),
        "sensitivity": config.get("scene", {}).get("sensitivity", 0.6),
        "stats": stats,
        "config": {
            "asr_engine": configured_asr,
            "effective_asr_engine": effective_asr,
            "asr_model": config.get("asr", {}).get("model_size", "base"),
            "asr_cloud_model": config.get("asr", {}).get("fun_asr", {}).get("model", "paraformer-realtime-v2"),
            "save_recordings": config.get("audio", {}).get("save_recordings", False),
            "tts_engine": configured_tts,
            "effective_tts_engine": effective_tts,
            "tts_model": config.get("api", {}).get("tts", {}).get("model", "sambert-zhichu-v1"),
            "tts_voice": config.get("tts", {}).get("voice", "zh-CN-XiaoxiaoNeural"),
            "learning_enabled": config.get("learning", {}).get("enabled", True),
            "media_guard": media_guard,
            "has_dashscope_key": has_dashscope_key,
            "dashscope_region": config.get("api", {}).get("dashscope_region", "beijing"),
            "llm": llm_display
        }
    })

@app.route("/api/events")
def events():
    """检测事件列表"""
    limit = request.args.get("limit", 20, type=int)
    events = get_recent_events(limit)
    return jsonify(events)

@app.route("/api/health")
def health():
    """设备健康状态，用于 Web 控制台展示。"""
    def systemctl_state(unit):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=3
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def dir_size(path):
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        except Exception:
            pass
        return total

    config = load_config()
    audio_dir = Path(os.getenv("VD_AUDIO_DIR") or config.get("audio", {}).get("save_dir") or PROJECT_ROOT / "audio")
    if not audio_dir.is_absolute():
        audio_dir = PROJECT_ROOT / audio_dir
    audio_count = 0
    if audio_dir.exists():
        try:
            audio_count = sum(1 for _ in audio_dir.glob("*.wav"))
        except Exception:
            audio_count = 0

    usage = shutil.disk_usage(PROJECT_ROOT)
    audio_bytes = dir_size(audio_dir)
    return jsonify({
        "ok": True,
        "host": socket.gethostname(),
        "services": {
            "detector": systemctl_state("language-violence-intervention-system.service"),
            "web": systemctl_state("language-violence-web.service"),
            "cleanup_timer": systemctl_state("language-violence-audio-cleanup.timer"),
            "upload_timer": systemctl_state("language-violence-audio-upload.timer")
        },
        "disk": {
            "total": f"{usage.total / 1024 / 1024 / 1024:.1f}G",
            "used": f"{usage.used / 1024 / 1024 / 1024:.1f}G",
            "free": f"{usage.free / 1024 / 1024 / 1024:.1f}G",
            "used_percent": f"{usage.used / usage.total * 100:.0f}%"
        },
        "audio": {
            "count": audio_count,
            "size": f"{audio_bytes / 1024 / 1024:.1f}MB",
            "save_recordings": config.get("audio", {}).get("save_recordings", False)
        }
    })

@app.route("/api/start", methods=["POST"])
def start():
    """启动主检测服务"""
    if is_main_running():
        return jsonify({"ok": True, "message": "已经在运行"})

    try:
        result = subprocess.run(
            ["sudo", "-n", "systemctl", "start", "language-violence-intervention-system.service"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return jsonify({"ok": False, "error": result.stderr.strip() or result.stdout.strip()}), 500
        return jsonify({"ok": True, "message": "启动成功"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/stop", methods=["POST"])
def stop():
    """停止主检测服务"""
    try:
        result = subprocess.run(
            ["sudo", "-n", "systemctl", "stop", "language-violence-intervention-system.service"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return jsonify({"ok": False, "error": result.stderr.strip() or result.stdout.strip()}), 500
        # 清理旧版本 Web 直接拉起的遗留主进程。
        subprocess.run(["pkill", "-f", str(PROJECT_ROOT / "src" / "main.py")], capture_output=True)
        return jsonify({"ok": True, "message": "已停止"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/config", methods=["GET"])
def get_config():
    """获取配置"""
    return jsonify(redacted_config(load_config()))

@app.route("/api/config", methods=["POST"])
def update_config():
    """更新配置"""
    try:
        data = request.get_json()
        config = load_stored_config()

        # 更新场景和灵敏度
        if "scene" in data:
            config.setdefault("scene", {})["default"] = data["scene"]
        if "sensitivity" in data:
            config.setdefault("scene", {})["sensitivity"] = data["sensitivity"]

        # 更新 ASR 引擎
        if "asr_engine" in data:
            config.setdefault("asr", {})["engine"] = data["asr_engine"]
        if "asr_model" in data:
            config.setdefault("asr", {})["model_size"] = data["asr_model"]

        persist_config(config)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== API Key 管理 ==========

@app.route("/api/config/key", methods=["POST"])
def update_api_key():
    """保存 DashScope API Key 或更新其地域设置。"""
    try:
        data = request.get_json()
        api_key = (data.get("api_key") or "").strip()

        if not api_key and not effective_dashscope_key():
            return jsonify({"ok": False, "error": "API Key 不能为空"}), 400

        config = load_stored_config()
        config.setdefault("api", {})
        config["api"]["dashscope_region"] = data.get("region", "beijing")
        if api_key and api_key not in SAVED_KEY_MARKERS:
            update_env_value("DASHSCOPE_API_KEY", api_key)
        persist_config(config)

        return jsonify({"ok": True, "message": "API Key 已保存，重启服务后生效"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== LLM / 模型配置 ==========

@app.route("/api/config/llm", methods=["POST"])
def update_llm_config():
    """保存 LLM 模型配置"""
    try:
        data = request.get_json()
        config = load_stored_config()
        api_cfg = config.setdefault("api", {})

        # 语义 LLM
        if "semantic" in data:
            sem = data["semantic"]
            sem_cfg = api_cfg.setdefault("semantic_llm", {})
            sem_cfg["provider"] = sem.get("provider", "dashscope")
            sem_cfg["model"] = sem.get("model", "")
            if sem.get("endpoint"):
                sem_cfg["endpoint"] = sem["endpoint"]
            if sem.get("api_key"):
                update_env_value("DASHSCOPE_API_KEY", sem["api_key"].strip())
            sem_cfg["model"] = sem.get("model") or sem_cfg.get("model", "qwen-plus")

        # 情绪 LLM
        if "emotion" in data:
            emo = data["emotion"]
            emo_cfg = api_cfg.setdefault("emotion_llm", {})
            emo_cfg["provider"] = emo.get("provider", "dashscope")
            emo_cfg["model"] = emo.get("model", "")
            if emo.get("endpoint"):
                emo_cfg["endpoint"] = emo["endpoint"]
            if emo.get("api_key"):
                update_env_value("DASHSCOPE_API_KEY", emo["api_key"].strip())
            emo_cfg["model"] = emo.get("model") or emo_cfg.get("model", "qwen-turbo")

        # ASR 配置
        if "asr" in data:
            asr = data["asr"]
            config.setdefault("asr", {})["engine"] = asr.get("engine", "ali_asr")
            if asr.get("model"):
                config["asr"].setdefault("fun_asr", {})["model"] = asr["model"]

        # TTS 配置
        if "tts" in data:
            tts = data["tts"]
            engine = tts.get("engine", "edge_tts")
            config.setdefault("tts", {})["engine"] = engine
            tts_api = config.setdefault("api", {}).setdefault("tts", {})
            if engine == "edge_tts" and tts.get("voice"):
                config["tts"]["voice"] = tts["voice"]
            if engine != "edge_tts" and tts.get("model"):
                tts_api["model"] = tts["model"]
                tts_api["voice"] = tts.get("voice") or tts["model"]

        persist_config(config)

        return jsonify({"ok": True, "message": "配置已保存，重启服务后生效"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== 获取 DashScope 模型列表 ==========

@app.route("/api/models/dashscope", methods=["GET"])
def list_dashscope_models():
    """获取 DashScope 模型和当前程序可调用的语音模型选项。"""
    try:
        config = load_config()
        api_key = config.get("api", {}).get("dashscope_api_key", "")
        if not api_key:
            return jsonify({"ok": False, "error": "请先配置 API Key"}), 400

        all_models = fetch_dashscope_compatible_models(api_key)

        return jsonify({
            "ok": True,
            "llm": [
                m for m in all_models
                if "qwen" in m.lower()
                and not any(tag in m.lower() for tag in ("image", "audio", "asr", "tts"))
            ][:15],
            "asr": [item["id"] for item in ASR_MODEL_OPTIONS],
            "asr_options": ASR_MODEL_OPTIONS,
            "tts": [item["id"] for item in SAMBERT_VOICE_OPTIONS],
            "tts_options": SAMBERT_VOICE_OPTIONS,
            "edge_tts_voices": EDGE_TTS_VOICE_OPTIONS,
            "all": all_models
        })
    except urllib.error.HTTPError as e:
        return jsonify({"ok": False, "error": f"HTTP {e.code}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== 测试 LLM ==========

@app.route("/api/llm/test", methods=["POST"])
def test_llm_api():
    """测试 LLM 连接并获取模型列表"""
    try:
        data = request.get_json()
        provider = data.get("provider", "")
        endpoint = (data.get("endpoint") or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip()
        api_key = effective_dashscope_key(data.get("api_key"))

        if not api_key:
            return jsonify({"ok": False, "error": "API Key 不能为空"}), 400

        headers = {"Authorization": f"Bearer {api_key}"}
        models_url = models_url_for_openai_compatible(endpoint)

        req = urllib.request.Request(models_url, headers=headers)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        models = []
        if provider == "ollama":
            for m in result.get("models", []):
                models.append(m.get("name", ""))
        else:
            for m in result.get("data", []):
                mid = m.get("id", "")
                if mid:
                    models.append(mid)

        # 尝试一次快速对话测试
        test_ok = False
        test_msg = ""
        test_model = data.get("model", "")

        if test_model and provider in ("dashscope", "openai") and api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=endpoint, timeout=15)
                resp = client.chat.completions.create(
                    model=test_model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5
                )
                test_ok = True
                test_msg = resp.choices[0].message.content or "OK"
            except Exception as te:
                test_msg = str(te)[:80]

        return jsonify({
            "ok": True,
            "models": models,
            "test_ok": test_ok,
            "test_msg": test_msg,
            "model_count": len(models)
        })
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:200]
        return jsonify({"ok": False, "error": f"HTTP {e.code}: {body}"}), 400
    except urllib.error.URLError as e:
        return jsonify({"ok": False, "error": f"连接失败: {e.reason}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== 测试 ASR ==========

@app.route("/api/asr/test", methods=["POST"])
def test_asr():
    """验证云端凭据，并返回此运行时支持的流式 ASR 模型。"""
    try:
        data = request.get_json(silent=True) or {}
        api_key = effective_dashscope_key(data.get("api_key"))

        if not api_key:
            return jsonify({"ok": False, "error": "请先配置 API Key"}), 400

        fetch_dashscope_compatible_models(api_key)

        return jsonify({
            "ok": True,
            "asr_models": [item["id"] for item in ASR_MODEL_OPTIONS],
            "asr_options": ASR_MODEL_OPTIONS,
            "asr_count": len(ASR_MODEL_OPTIONS)
        })
    except urllib.error.HTTPError as e:
        return jsonify({"ok": False, "error": f"HTTP {e.code}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ========== TTS 测试播放 ==========

@app.route("/api/tts/test/playback", methods=["POST"])
def test_tts_playback():
    """Synthesize the submitted preview text and play it on the configured speaker."""
    try:
        data = request.get_json(silent=True) or {}
        config = load_config()
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "请输入试播文字"}), 400
        text = text[:200]
        engine = (data.get("engine") or config.get("tts", {}).get("engine", "edge_tts")).strip()

        if engine == "edge_tts":
            from tts_engine import TTSEngine
            allowed_voices = {item["id"] for item in EDGE_TTS_VOICE_OPTIONS}
            voice = (data.get("voice") or config.get("tts", {}).get("voice") or EDGE_TTS_VOICE_OPTIONS[0]["id"]).strip()
            if voice not in allowed_voices:
                voice = EDGE_TTS_VOICE_OPTIONS[0]["id"]
            tts = TTSEngine(voice=voice)
            tts.load()
            played = tts.speak(text)
            detail = voice
        elif engine in {"sambert", "ali_tts"}:
            from ali_tts_engine import AliTTSEngine
            api_key = effective_dashscope_key(data.get("api_key"))
            if not api_key:
                return jsonify({"ok": False, "error": "请先配置 API Key"}), 400
            allowed_models = {item["id"] for item in SAMBERT_VOICE_OPTIONS}
            model = (data.get("model") or config.get("api", {}).get("tts", {}).get("model") or "sambert-zhichu-v1").strip()
            if model not in allowed_models:
                return jsonify({"ok": False, "error": "请选择可用的 SamBERT 音色"}), 400
            tts = AliTTSEngine(api_key=api_key, model=model, voice=model)
            tts.load()
            played = tts.speak(text)
            detail = model
        else:
            return jsonify({"ok": False, "error": "当前仅支持 Edge TTS 或 SamBERT 试听"}), 400

        if not played:
            return jsonify({"ok": False, "error": "语音已请求，但音箱播放失败"}), 500
        return jsonify({
            "ok": True,
            "engine": engine,
            "voice": detail,
            "message": "语音试听播放成功"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/tts/test", methods=["POST"])
def test_tts():
    """验证云端凭据，并返回 SamBERT 可选音色。"""
    try:
        data = request.get_json(silent=True) or {}
        api_key = effective_dashscope_key(data.get("api_key"))

        if not api_key:
            return jsonify({"ok": False, "error": "请先配置 API Key"}), 400

        fetch_dashscope_compatible_models(api_key)

        return jsonify({
            "ok": True,
            "tts_models": [item["id"] for item in SAMBERT_VOICE_OPTIONS],
            "tts_options": SAMBERT_VOICE_OPTIONS,
            "edge_tts_voices": EDGE_TTS_VOICE_OPTIONS,
            "tts_count": len(SAMBERT_VOICE_OPTIONS)
        })
    except urllib.error.HTTPError as e:
        return jsonify({"ok": False, "error": f"HTTP {e.code}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500








# ========== 事件标记 API ==========

@app.route('/api/events/mark', methods=['POST'])
def mark_event():
    """标记事件为疑问/误报/确认，同时通知学习引擎"""
    try:
        data = request.json
        event_ts = data.get('ts')
        mark_type = data.get('mark')
        
        if not event_ts or not mark_type:
            return jsonify({"ok": False, "error": "缺少参数"})
        
        # 1. 写入标记文件
        marks_file = LOG_DIR / "event_marks.json"
        marks = {}
        if marks_file.exists():
            os.chmod(marks_file, 0o600)
            with open(marks_file, 'r', encoding='utf-8') as f:
                marks = json.load(f)
        
        marks[str(event_ts)] = {
            "mark": mark_type,
            "marked_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(marks_file, 'w', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as f:
            json.dump(marks, f, ensure_ascii=False, indent=2)
        os.chmod(marks_file, 0o600)
        
        # 2. 查找事件数据并转发给学习引擎
        if LEARNING_ENABLED and EVENTS_FILE.exists():
            try:
                # 在 events.jsonl 中查找匹配的事件
                lines = EVENTS_FILE.read_text(encoding="utf-8").strip().split("\n")
                event_data = None
                for line in reversed(lines):  # 从最新开始找
                    if line.strip():
                        try:
                            evt = json.loads(line)
                            # 使用近似匹配（浮点精度）
                            if abs(evt.get("ts", 0) - float(event_ts)) < 0.001:
                                event_data = evt
                                break
                        except Exception:
                            pass
                
                if event_data:
                    # 映射标记类型到学习反馈类型
                    feedback_map = {
                        "doubt": "false_negative",
                        "false_positive": "false_positive",
                        "confirmed": "confirmed"
                    }
                    feedback_type = feedback_map.get(mark_type, mark_type)
                    learning_engine.add_feedback(event_data, feedback_type)
            except Exception as e:
                print(f"[Mark] 学习引擎通知失败: {e}", flush=True)
        
        return jsonify({"ok": True, "mark": mark_type})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/events/marks')
def get_marks():
    """获取所有标记"""
    try:
        marks_file = LOG_DIR / "event_marks.json"
        if marks_file.exists():
            os.chmod(marks_file, 0o600)
            with open(marks_file, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify({})
    except:
        return jsonify({})

# ========== 学习引擎 API ==========

@app.route('/api/learning/feedback', methods=['POST'])
def submit_learning_feedback():
    # 提交详细反馈到学习引擎
    try:
        if not LEARNING_ENABLED:
            return jsonify({'ok': False, 'error': '学习引擎未启用'})
        
        data = request.json
        event_data = data.get("event_data", {})
        feedback_type = data.get("feedback_type")  # false_positive, false_negative, confirmed
        user_note = data.get("user_note", "")
        
        if not event_data or not feedback_type:
            return jsonify({'ok': False, 'error': '缺少参数'})
        
        result = learning_engine.add_feedback(event_data, feedback_type, user_note)
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/learning/analyze', methods=['POST'])
def analyze_learning():
    # 触发学习分析
    try:
        if not LEARNING_ENABLED:
            return jsonify({'ok': False, 'error': '学习引擎未启用'})
        
        result = learning_engine.analyze_and_learn()
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/learning/report')
def get_learning_report():
    # 获取学习报告
    try:
        if not LEARNING_ENABLED:
            return jsonify({'ok': False, 'error': '学习引擎未启用'})
        
        result = learning_engine.get_learning_report()
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/learning/thresholds')
def get_learning_thresholds():
    # 获取当前学习到的阈值
    try:
        if not LEARNING_ENABLED:
            return jsonify({'ok': False, 'error': '学习引擎未启用'})
        
        return jsonify({
            'ok': True,
            'thresholds': learning_engine.thresholds,
            'stats': learning_engine.stats
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/learning/speaker/<speaker>')
def get_speaker_learning_profile(speaker):
    # 获取说话人学习画像
    try:
        if not LEARNING_ENABLED:
            return jsonify({'ok': False, 'error': '学习引擎未启用'})

        result = learning_engine.get_speaker_profile(speaker)
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ========== 事件导出 API ==========

@app.route('/api/events/export', methods=['GET'])
def export_events():
    """导出事件到 CSV 文件"""
    try:
        import csv
        from datetime import datetime

        start_date = request.args.get('start', '')
        end_date = request.args.get('end', '')

        events = get_all_events()

        # 日期筛选
        if start_date or end_date:
            filtered = []
            for e in events:
                ts = e.get('timestamp', '')[:10]
                if start_date and ts < start_date:
                    continue
                if end_date and ts > end_date:
                    continue
                filtered.append(e)
            events = filtered

        if not events:
            return jsonify({'ok': False, 'error': '无事件可导出'}), 400

        filename = f"events_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        import io
        output = io.StringIO()
        headers = [
            '时间', '文本', '情绪类型', '情绪强度', '情绪分',
            '暴力类型', '暴力置信度', '严重度', '是否暴力',
            '说话人', '声纹已匹配', '声纹分数', '声纹阈值', '场景', '已干预', '干预文本', '干预阈值',
            '音量等级', '音量RMS', '音量突变', '语调F0', '语调趋势',
            '声学风险分', '声学风险因素'
        ]
        field_keys = [
            'timestamp', 'text', 'emotion_type', 'emotion_intensity', 'emotion_score',
            'violence_type', 'violence_confidence', 'violence_severity', 'is_violence',
            'speaker', 'speaker_verified', 'speaker_match_score', 'speaker_match_threshold',
            'scene', 'intervention_triggered', 'intervention_text', 'intervention_threshold',
            'volume_level', 'volume_rms', 'volume_spike', 'pitch_f0', 'pitch_trend',
            'acoustic_risk_score', 'acoustic_risk_factors'
        ]

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for e in events:
            row = {}
            for h, k in zip(headers, field_keys):
                row[h] = display_value(k, e.get(k, ''))
            writer.writerow(row)

        return jsonify({
            'ok': True,
            'filename': filename,
            'count': len(events),
            'csv_data': output.getvalue()
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 说话人列表 API ==========

@app.route('/api/speakers', methods=['GET'])
def get_speakers():
    """获取基于内容观察和人工维护记录的画像列表。"""
    try:
        events = get_all_events()
        speakers = build_speaker_profile_engine().list_profiles(events, current_learning_profiles())
        return jsonify({
            'ok': True,
            'speakers': speakers,
            'content_notice': '画像仅按已记录的说话内容与互动事件形成观察摘要，不读取声纹模板，不构成心理诊断。'
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/speakers/<path:speaker_id>/profile', methods=['GET'])
def get_observed_speaker_profile(speaker_id):
    """获取某个说话人的可审计画像详情。"""
    try:
        events = get_all_events()
        engine = build_speaker_profile_engine()
        if not engine.has_record(speaker_id, events):
            return jsonify({'ok': False, 'error': '档案不存在'}), 404
        profile = complete_speaker_profile(
            speaker_id, events, current_learning_profiles().get(speaker_id)
        )
        return jsonify({'ok': True, 'profile': profile})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/speakers', methods=['POST'])
def create_speaker_record():
    """新建人工档案；不将其伪装为已确认声纹身份。"""
    try:
        data = request.get_json(silent=True) or {}
        engine = build_speaker_profile_engine()
        speaker_id = engine.create_profile(data)
        profile = complete_speaker_profile(speaker_id, get_all_events())
        return jsonify({'ok': True, 'profile': profile}), 201
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/speakers/<path:speaker_id>', methods=['PATCH'])
def update_speaker_record(speaker_id):
    """保存说话人的人工备注、关系与关注级别。"""
    try:
        events = get_all_events()
        engine = build_speaker_profile_engine()
        if not engine.has_record(speaker_id, events):
            return jsonify({'ok': False, 'error': '档案不存在'}), 404
        engine.update_profile(speaker_id, request.get_json(silent=True) or {})
        profile = complete_speaker_profile(
            speaker_id, events, current_learning_profiles().get(speaker_id)
        )
        return jsonify({'ok': True, 'profile': profile})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 本人自愿心理筛查 API ==========

@app.route('/api/screenings/instruments', methods=['GET'])
def get_screening_instruments():
    """Expose self-report instrument items; spoken content is never auto-scored as a scale."""
    return jsonify({
        'ok': True,
        'instruments': build_mental_screening_engine().instruments(),
        'notice': 'PHQ-9 与 GAD-7 仅可由本人自愿填写；得分用于筛查提示，不属于医疗诊断。',
    })

@app.route('/api/speakers/<path:speaker_id>/screenings', methods=['POST'])
def submit_speaker_screening(speaker_id):
    """Store a consented self-report score separately from observed speech content."""
    try:
        events = get_all_events()
        profile_engine = build_speaker_profile_engine()
        if not profile_engine.has_record(speaker_id, events):
            return jsonify({'ok': False, 'error': '档案不存在'}), 404
        if speaker_id.strip().lower() in {"unknown", "未知", "模拟用户"} or "模拟" in speaker_id:
            return jsonify({'ok': False, 'error': '请先创建具名档案，再由本人提交心理筛查'}), 400
        data = request.get_json(silent=True) or {}
        with _mental_screening_lock:
            result = build_mental_screening_engine().submit(
                speaker_id=speaker_id,
                instrument=str(data.get('instrument') or ''),
                answers=data.get('answers'),
                consent=data.get('consent') is True,
                self_report=data.get('self_report') is True,
            )
        safety_case = None
        if result.get("urgent"):
            with _safety_case_lock:
                safety_case = build_safety_case_engine().create_screening_alert(speaker_id, result)
        profile = complete_speaker_profile(
            speaker_id, events, current_learning_profiles().get(speaker_id)
        )
        return jsonify({
            'ok': True,
            'screening': result,
            'profile': profile,
            'safety_case': safety_case,
        })
    except ScreeningError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/speakers/<path:speaker_id>/screenings', methods=['DELETE'])
def delete_speaker_screenings(speaker_id):
    """Allow local withdrawal of all voluntarily submitted screening scores."""
    try:
        events = get_all_events()
        profile_engine = build_speaker_profile_engine()
        if not profile_engine.has_record(speaker_id, events):
            return jsonify({'ok': False, 'error': '档案不存在'}), 404
        with _mental_screening_lock:
            removed = build_mental_screening_engine().clear(speaker_id)
        profile = complete_speaker_profile(
            speaker_id, events, current_learning_profiles().get(speaker_id)
        )
        return jsonify({'ok': True, 'removed': removed, 'profile': profile})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 人工安全处置 API ==========

@app.route('/api/safety/cases', methods=['GET'])
def get_safety_cases():
    """List high-priority items that require a documented human response."""
    try:
        limit = max(1, min(request.args.get('limit', 50, type=int), 200))
        return jsonify(build_safety_case_engine().list_cases(get_all_events(), limit=limit))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/safety/cases/<path:case_id>', methods=['PATCH'])
def update_safety_case(case_id):
    """Acknowledge or close a safety item with a human action trail."""
    try:
        with _safety_case_lock:
            result = build_safety_case_engine().update_case(
                case_id=case_id,
                events=get_all_events(),
                updates=request.get_json(silent=True) or {},
                actor=request.authorization.username if request.authorization else "console",
            )
        return jsonify({'ok': True, 'case': result})
    except SafetyCaseError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 电视/歌曲媒体声过滤 API ==========

@app.route('/api/media-guard', methods=['GET'])
def get_media_guard():
    """Return local playback-filter calibration and suppression status."""
    try:
        return jsonify(build_media_guard_engine().status())
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/media-guard/config', methods=['POST'])
def configure_media_guard():
    """Persist conservative media suppression settings."""
    try:
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "balanced")
        if mode not in MediaGuard.MODES:
            return jsonify({'ok': False, 'error': '无效的过滤模式'}), 400
        config = load_stored_config()
        section = config.setdefault("media_guard", {})
        section["enabled"] = data.get("enabled") is True
        section["mode"] = mode
        section.setdefault("match_margin", 0.035)
        section.setdefault("max_media_distance", 0.17)
        section.setdefault("shouting_bypass_rms", 2500)
        section.setdefault("calibration_seconds", 5)
        persist_config(config)
        return jsonify({
            'ok': True,
            'message': '媒体声过滤设置已保存，重启检测服务后生效',
            'media_guard': build_media_guard_engine().status(),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/media-guard/calibrate/<kind>', methods=['POST'])
def calibrate_media_guard(kind):
    """Capture one local playback or consented human reference sample."""
    try:
        data = request.get_json(silent=True) or {}
        if kind not in MediaGuard.KINDS:
            return jsonify({'ok': False, 'error': '请选择媒体播放或真人语音样本'}), 400
        if kind == "human" and data.get("consent") is not True:
            return jsonify({'ok': False, 'error': '采集真人语音样本前需取得本人知情同意'}), 400
        if data.get("confirm_source") is not True:
            return jsonify({'ok': False, 'error': '请确认当前采集的声音来源'}), 400
        duration = float(load_config().get("media_guard", {}).get("calibration_seconds", 5))
        duration = max(3.0, min(8.0, duration))
        if not _voiceprint_capture_lock.acquire(blocking=False):
            return jsonify({'ok': False, 'error': '已有声音采集正在进行'}), 409
        try:
            engine = build_media_guard_engine()
            status = capture_voiceprint_audio(
                duration,
                lambda audio: engine.calibrate(kind, audio, consent=data.get("consent") is True),
            )
        finally:
            _voiceprint_capture_lock.release()
        return jsonify({
            'ok': True,
            'message': '声学特征模板已保存至本机，未保存原始音频',
            'media_guard': status,
        })
    except (MediaGuardError, VoiceprintError) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/media-guard/calibrate/<kind>', methods=['DELETE'])
def clear_media_guard_samples(kind):
    """Withdraw local acoustic reference samples."""
    try:
        status = build_media_guard_engine().clear(kind)
        if is_main_running():
            control_detector_service("restart")
        return jsonify({'ok': True, 'media_guard': status})
    except MediaGuardError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 独立本地声纹管理 API ==========

@app.route('/api/voiceprints', methods=['GET'])
def get_voiceprint_status():
    """Expose enrollment metadata only; embeddings never leave local storage."""
    try:
        return jsonify(build_voiceprint_engine().status())
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/voiceprints/<path:speaker_id>', methods=['GET'])
def get_voiceprint_profile_status(speaker_id):
    """Return biometric enrollment state without mixing it into content portraits."""
    try:
        profile_engine, events = voiceprint_profile_or_error(speaker_id)
        profile = profile_engine.build_profile(
            speaker_id, events, current_learning_profiles().get(speaker_id)
        )
        return jsonify({
            'ok': True,
            'speaker_id': speaker_id,
            'display_name': profile.get('display_name', speaker_id),
            'voiceprint': build_voiceprint_engine().get_speaker_status(speaker_id),
        })
    except VoiceprintError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

def voiceprint_profile_or_error(speaker_id):
    events = get_all_events()
    profile_engine = build_speaker_profile_engine()
    if not profile_engine.has_record(speaker_id, events):
        raise VoiceprintError("请先保存人员档案")
    if speaker_id.strip().lower() in {"unknown", "未知", "模拟用户"} or "模拟" in speaker_id:
        raise VoiceprintError("未识别说话人不能注册声纹，请先新建具名档案")
    return profile_engine, events

@app.route('/api/voiceprints/<path:speaker_id>/enroll', methods=['POST'])
def enroll_voiceprint(speaker_id):
    """Capture one consented enrollment sample through the device microphone."""
    data = request.get_json(silent=True) or {}
    if data.get("consent") is not True:
        return jsonify({'ok': False, 'error': '请先确认已取得本人知情同意'}), 400
    try:
        profile_engine, events = voiceprint_profile_or_error(speaker_id)
        duration = float(load_config().get("voiceprint", {}).get("capture_seconds", 5))
        duration = max(3.0, min(8.0, duration))
        if not _voiceprint_capture_lock.acquire(blocking=False):
            return jsonify({'ok': False, 'error': '已有声纹采集正在进行'}), 409
        try:
            engine = build_voiceprint_engine(load_model=True)
            voiceprint = capture_voiceprint_audio(
                duration, lambda audio: engine.enroll(speaker_id, audio)
            )
        finally:
            _voiceprint_capture_lock.release()
        return jsonify({
            'ok': True,
            'message': '声纹模板已保存至本机，未保留采集原音频',
            'voiceprint': voiceprint,
        })
    except VoiceprintError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/voiceprints/<path:speaker_id>/test', methods=['POST'])
def test_voiceprint_recognition(speaker_id):
    """Capture a consented sample and report whether it matches this profile."""
    data = request.get_json(silent=True) or {}
    if data.get("consent") is not True:
        return jsonify({'ok': False, 'error': '请先确认已取得本人知情同意'}), 400
    try:
        voiceprint_profile_or_error(speaker_id)
        if not _voiceprint_capture_lock.acquire(blocking=False):
            return jsonify({'ok': False, 'error': '已有声纹采集正在进行'}), 409
        try:
            engine = build_voiceprint_engine(load_model=True)
            if not engine.get_speaker_status(speaker_id)["enrolled"]:
                raise VoiceprintError("该档案尚未注册声纹")
            match = capture_voiceprint_audio(4.0, engine.identify_with_score)
        finally:
            _voiceprint_capture_lock.release()
        match["requested_speaker_id"] = speaker_id
        match["matches_profile"] = bool(match.get("matched") and match.get("speaker_id") == speaker_id)
        return jsonify({'ok': True, 'match': match})
    except VoiceprintError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/voiceprints/<path:speaker_id>', methods=['DELETE'])
def delete_voiceprint(speaker_id):
    """Delete locally held biometric templates for this profile."""
    try:
        profile_engine, events = voiceprint_profile_or_error(speaker_id)
        if not _voiceprint_capture_lock.acquire(blocking=False):
            return jsonify({'ok': False, 'error': '声纹采集或测试正在进行，请完成后再删除模板'}), 409
        try:
            detector_was_running = is_main_running()
            removed = build_voiceprint_engine().remove(speaker_id)
            if removed and detector_was_running:
                control_detector_service("restart")
        finally:
            _voiceprint_capture_lock.release()
        voiceprint = build_voiceprint_engine().get_speaker_status(speaker_id)
        return jsonify({'ok': True, 'removed': removed, 'voiceprint': voiceprint})
    except VoiceprintError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ========== 干预日志 API ==========

@app.route('/api/interventions', methods=['GET'])
def get_interventions():
    """获取所有干预记录"""
    try:
        limit = max(1, min(request.args.get('limit', 50, type=int), 200))
        events = reversed(get_recent_events(limit=max(limit * 5, 50)))
        interventions = [
            e for e in events
            if e.get('intervention_triggered') or e.get('is_violence')
        ]
        interventions = interventions[:limit]

        return jsonify({
            'ok': True,
            'count': len(interventions),
            'interventions': [
                {
                    'ts': e.get('ts'),
                    'timestamp': e.get('timestamp', ''),
                    'text': e.get('text', ''),
                    'violence_type': e.get('violence_type', ''),
                    'violence_confidence': e.get('violence_confidence', 0),
                    'severity': e.get('violence_severity', ''),
                    'emotion_type': e.get('emotion_type', ''),
                    'speaker': e.get('speaker', ''),
                    'scene': e.get('scene', ''),
                    'intervention_text': e.get('intervention_text', ''),
                    'intervention_triggered': bool(e.get('intervention_triggered')),
                }
                for e in interventions
            ]
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ========== 实时干预通知 (SSE) ==========

@app.route('/api/events/stream')
def events_stream():
    """Legacy SSE endpoint: do not keep a scarce web worker occupied."""
    return Response(
        'retry: 15000\n\n',
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )

# ========== 趋势统计 API ==========

@app.route('/api/stats/trend', methods=['GET'])
def get_trend_stats():
    """获取每日事件趋势统计"""
    try:
        days = max(3, min(request.args.get('days', 7, type=int), 90))
        events = get_all_events()
        today = datetime.now().date()
        sorted_dates = [
            (today - timedelta(days=offset)).strftime('%Y-%m-%d')
            for offset in reversed(range(days))
        ]
        daily = {
            day: {'total': 0, 'violence': 0, 'acoustic': 0, 'intervention': 0}
            for day in sorted_dates
        }

        for e in events:
            date = e.get('timestamp', '')[:10]
            if date not in daily:
                continue
            daily[date]['total'] += 1
            if e.get('is_violence'):
                daily[date]['violence'] += 1
            if e.get('acoustic_risk_score', 0) >= 60:
                daily[date]['acoustic'] += 1
            if e.get('intervention_triggered'):
                daily[date]['intervention'] += 1

        labels = sorted_dates
        totals = [daily[d]['total'] for d in sorted_dates]
        violences = [daily[d]['violence'] for d in sorted_dates]
        acoustics = [daily[d]['acoustic'] for d in sorted_dates]
        interventions = [daily[d]['intervention'] for d in sorted_dates]

        return jsonify({
            'ok': True,
            'labels': labels,
            'datasets': {
                'total': totals,
                'violence': violences,
                'acoustic': acoustics,
                'intervention': interventions
            }
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ========== 趋势报告 API ==========

@app.route('/api/reports/daily', methods=['GET'])
def get_daily_report():
    """获取日报"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        date_str = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
        report = engine.generate_daily_report(date_str)
        return jsonify({'ok': True, 'report': report})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/reports/weekly', methods=['GET'])
def get_weekly_report():
    """获取周报"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        offset = request.args.get('offset', 0, type=int)
        date_str = request.args.get('date')
        report = engine.generate_weekly_report(offset, date_str)
        return jsonify({'ok': True, 'report': report})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/reports/monthly', methods=['GET'])
def get_monthly_report():
    """获取月报"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        year = request.args.get('year', datetime.now().year, type=int)
        month = request.args.get('month', datetime.now().month, type=int)
        report = engine.generate_monthly_report(year, month)
        return jsonify({'ok': True, 'report': report})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/reports/overview', methods=['GET'])
def get_reports_overview():
    """获取总览数据"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        days = request.args.get('days', 30, type=int)
        overview = engine.generate_overview(days)
        return jsonify({'ok': True, 'overview': overview})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/reports/save', methods=['POST'])
def save_report():
    """保存当前报告"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        data = request.get_json() or {}
        rtype = data.get('type', 'daily')
        if rtype == 'weekly':
            report = engine.generate_weekly_report(data.get('offset', 0), data.get('date'))
        elif rtype == 'monthly':
            report = engine.generate_monthly_report(data.get('year'), data.get('month'))
        else:
            report = engine.generate_daily_report(data.get('date'))
        path = engine.save_report(report)
        return jsonify({'ok': True, 'path': path})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/reports/list', methods=['GET'])
def list_reports():
    """列出已保存的报告"""
    try:
        from trend_report_engine import TrendReportEngine
        engine = TrendReportEngine(
            log_dir=str(Path(__file__).parent / "logs"),
            data_dir=str(Path(__file__).parent / "data")
        )
        reports = engine.get_latest_reports(limit=20)
        return jsonify({'ok': True, 'reports': reports})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ========== 完整配置读写 API ==========

@app.route('/api/config/full', methods=['GET'])
def get_full_config():
    """获取完整配置（含隐藏字段）"""
    return jsonify(redacted_config(load_config()))

@app.route('/api/config/full', methods=['POST'])
def update_full_config():
    """更新完整配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': '无数据'}), 400

        config = load_stored_config()

        # 深度合并策略
        def deep_merge(base, updates):
            for key, val in updates.items():
                if isinstance(val, dict) and isinstance(base.get(key), dict):
                    deep_merge(base[key], val)
                else:
                    base[key] = val

        deep_merge(config, data)

        persist_config(config)

        return jsonify({'ok': True, 'message': '配置已保存'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

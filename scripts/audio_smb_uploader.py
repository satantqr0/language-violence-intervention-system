#!/usr/bin/env python3
"""
语音文件 SMB 上传脚本。

通过环境变量配置 SMB，适合由 systemd timer 定时执行。
上传成功后会删除本地 wav 文件。
"""

import os
import sys
from pathlib import Path
from smb.SMBConnection import SMBConnection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from env_loader import load_env_file
    load_env_file(PROJECT_ROOT / ".env")
except Exception:
    pass

SMB_HOST = os.getenv("SMB_HOST", "")
SMB_PORT = int(os.getenv("SMB_PORT", "445"))
SMB_USER = os.getenv("SMB_USER", "")
SMB_PASS = os.getenv("SMB_PASS", "")
SMB_SHARE = os.getenv("SMB_SHARE", "")
SMB_FOLDER = os.getenv("SMB_FOLDER", "语音文件")
SMB_CLIENT_NAME = os.getenv("SMB_CLIENT_NAME", "pi-vd")
SMB_SERVER_NAME = os.getenv("SMB_SERVER_NAME", "smb-server")
LOCAL_AUDIO_DIR = os.getenv("VD_AUDIO_DIR", str(PROJECT_ROOT / "audio"))


def log(msg):
    print(f"[SMB] {msg}", flush=True)


def validate_config():
    missing = [
        name for name, value in {
            "SMB_USER": SMB_USER,
            "SMB_PASS": SMB_PASS,
            "SMB_SHARE": SMB_SHARE,
        }.items()
        if not value
    ]
    if missing:
        log(f"缺少环境变量: {', '.join(missing)}")
        return False
    return True


def upload_to_smb():
    if not validate_config():
        return False

    try:
        conn = SMBConnection(
            SMB_USER,
            SMB_PASS,
            SMB_CLIENT_NAME,
            SMB_SERVER_NAME,
            use_ntlm_v2=True,
        )
        if not conn.connect(SMB_HOST, SMB_PORT):
            log("连接失败")
            return False
        log("已连接 SMB")
    except Exception as e:
        log(f"连接异常: {e}")
        return False

    try:
        conn.listPath(SMB_SHARE, "/" + SMB_FOLDER)
    except Exception:
        try:
            conn.createDirectory(SMB_SHARE, "/" + SMB_FOLDER)
            log(f"创建目录: {SMB_FOLDER}")
        except Exception as e:
            log(f"创建目录失败: {e}")

    audio_dir = Path(LOCAL_AUDIO_DIR)
    if not audio_dir.exists():
        log(f"本地目录不存在: {LOCAL_AUDIO_DIR}")
        return True

    wav_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.WAV"))
    if not wav_files:
        log("无 wav 文件需要上传")
        return True

    log(f"发现 {len(wav_files)} 个 wav 文件待上传")

    uploaded = 0
    deleted = 0
    for wav in wav_files:
        try:
            remote_file = f"/{SMB_FOLDER}/{wav.name}"
            with open(wav, "rb") as f:
                conn.storeFile(SMB_SHARE, remote_file, f)
            size_kb = wav.stat().st_size / 1024
            log(f"上传: {wav.name} ({size_kb:.1f}KB)")
            wav.unlink()
            deleted += 1
            uploaded += 1
        except Exception as e:
            log(f"失败: {wav.name} - {e}")

    log(f"完成: 上传 {uploaded} 个，删除 {deleted} 个")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if upload_to_smb() else 1)

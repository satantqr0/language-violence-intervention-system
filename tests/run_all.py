#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行全部测试 — 统一测试框架
"""

import subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = [
    "tests/test_acoustic_analyzer.py",
    "tests/test_semantic_analyzer.py",
    "tests/test_event_logger.py",
    "tests/test_scene_manager.py",
    "tests/test_trend_report_engine.py",
    "tests/test_speaker_profile_engine.py",
    "tests/test_mental_screening_engine.py",
    "tests/test_safety_case_engine.py",
    "tests/test_media_guard.py",
    "tests/test_learning_engine_privacy.py",
    "tests/test_voiceprint.py",
    "tests/test_web_security.py",
    "tests/test_tts_engine.py",
]

failed = 0
for f in files:
    path = os.path.join(ROOT, f)
    print(f"\n{'='*60}\n  ▶ python {f}\n{'='*60}")
    code = subprocess.run([sys.executable, path]).returncode
    if code != 0:
        failed += 1

print(f"\n{'='*60}")
if failed == 0:
    print("  ✅ 全部测试通过")
else:
    print(f"  ❌ {failed} 个测试文件有失败")
print(f"{'='*60}")
sys.exit(failed)

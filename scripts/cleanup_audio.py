#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean old saved audio files for the violence detector."""

import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = Path(os.getenv("VD_AUDIO_DIR", PROJECT_ROOT / "audio"))
RETENTION_DAYS = int(os.getenv("VD_AUDIO_RETENTION_DAYS", "7"))
MAX_BYTES = int(float(os.getenv("VD_AUDIO_MAX_GB", "2")) * 1024 * 1024 * 1024)


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in AUDIO_DIR.glob("*.wav") if p.is_file()]
    now = time.time()
    cutoff = now - RETENTION_DAYS * 86400
    removed = 0
    freed = 0

    for path in files:
        try:
            stat = path.stat()
            if stat.st_mtime < cutoff:
                size = stat.st_size
                path.unlink()
                removed += 1
                freed += size
        except FileNotFoundError:
            pass

    files = [p for p in AUDIO_DIR.glob("*.wav") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    if total > MAX_BYTES:
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= MAX_BYTES:
                break
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
                removed += 1
                freed += size
            except FileNotFoundError:
                pass

    print(f"audio cleanup: removed={removed} freed_mb={freed / 1024 / 1024:.1f} remaining_mb={total / 1024 / 1024:.1f}")


if __name__ == "__main__":
    main()

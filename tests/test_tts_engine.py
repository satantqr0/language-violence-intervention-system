#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS output-device selection regression tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tts_engine import order_alsa_playback_devices


APLAY_WITH_SPEAKER = """\
card 0: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
card 2: ArrayUAC10 [ReSpeaker 4 Mic Array (UAC1.0)], device 0: USB Audio [USB Audio]
card 3: BR17 [JieLi BR17], device 0: USB Audio [USB Audio]
"""


def test_usb_speaker_precedes_microphone_array():
    devices = order_alsa_playback_devices(APLAY_WITH_SPEAKER)
    assert devices == [
        "plughw:CARD=BR17,DEV=0",
        "plughw:CARD=ArrayUAC10,DEV=0",
    ]


def test_microphone_array_output_remains_fallback():
    devices = order_alsa_playback_devices(
        "card 2: ArrayUAC10 [ReSpeaker 4 Mic Array (UAC1.0)], device 0: USB Audio [USB Audio]\n"
    )
    assert devices == ["plughw:CARD=ArrayUAC10,DEV=0"]


def run_tests():
    total = passed = failed = 0
    for name in sorted(name for name in globals() if name.startswith("test_")):
        total += 1
        try:
            globals()[name]()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")
            failed += 1
    print(f"\n{'='*50}\n  Result: {passed}/{total} passed  {failed}/{total} failed\n{'='*50}")
    return failed


if __name__ == "__main__":
    raise SystemExit(run_tests())

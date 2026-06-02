# Third-Party Notices

This file summarizes known runtime dependency licenses for the open-source
preparation branch. It is informational and does not modify the Apache License
2.0 for this project.

The repository does not vendor these packages. If you redistribute dependency
wheels, binary images, model files, operating-system packages, or a bundled
device image, you must keep the corresponding third-party license texts and
notices for the exact versions you distribute.

License metadata below was checked from PyPI package metadata on 2026-06-02.
Pinned releases or downstream package builds may include additional notices.

| Dependency | License metadata | Notes |
|------------|------------------|-------|
| numpy | BSD-3-Clause, 0BSD, MIT, Zlib, CC0-1.0 metadata | Scientific computing dependency |
| torch | BSD-3-Clause | PyTorch runtime dependency |
| torchaudio | BSD License classifier | PyTorch audio dependency |
| pyaudio | MIT | Python PortAudio bindings |
| opuslib | BSD 3-Clause License | Opus codec bindings |
| scipy | BSD License classifier | Scientific computing dependency |
| speechbrain | Apache-2.0 | Optional local voiceprint feature extraction |
| openai-whisper | MIT | Optional local Whisper ASR package |
| faster-whisper | MIT | Optional alternative Whisper runtime |
| edge-tts | LGPLv3 classifier | Optional TTS package; keep its license terms if bundled |
| Flask | BSD-3-Clause | Web console framework |
| gunicorn | MIT | Optional production WSGI server |
| openai | Apache-2.0 | Optional API client |
| dashscope | Apache 2.0 | Optional DashScope API client |
| pysmb | zlib/libpng | Optional SMB upload dependency |
| PyYAML | MIT | Configuration parsing dependency |

Model weights, cloud APIs, online speech services, hardware devices, operating
system packages, and third-party media are not licensed by this project. Review
their separate licenses and service terms before redistribution or commercial
deployment.

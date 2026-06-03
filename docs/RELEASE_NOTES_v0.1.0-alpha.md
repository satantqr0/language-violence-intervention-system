# v0.1.0-alpha Release Notes

This is the first alpha release of Language Violence Intervention System, a
privacy-first edge AI prototype for verbal-abuse detection and gentle
intervention.

## What Is Included

- Protected WebUI for status, events, settings, export, trend reports, and
  safety-case review.
- Local-first ASR path with Whisper, plus configurable DashScope ASR/LLM/TTS
  integrations.
- Rule-based semantic detection with optional LLM semantic analysis.
- Acoustic risk analysis for volume, pitch, shouting, and abnormal changes.
- TTS intervention prompts for non-aggressive reminders.
- Speaker profile view based on transcribed content observation.
- Experimental local voiceprint enrollment and recognition.
- TV/song media-sound filtering with local acoustic calibration.
- Raspberry Pi 5 deployment scripts and systemd service setup.
- Chinese and English README files with screenshots and demo visuals.
- Apache License 2.0, NOTICE, legal notice, contribution guide, third-party
  notices, and roadmap.

## Validation

- Automated regression tests: `130/130` passed with `python3 tests/run_all.py`.
- Real-device baseline: Raspberry Pi 5 8GB deployment path has been used as the
  primary hardware baseline.
- Screenshots use anonymous demo data only. They do not include real household
  recordings, voiceprint templates, event logs, or personal profiles.

## Known Limitations

- This is an alpha-stage prototype, not a production safety system.
- False positive, false negative, and intervention-effectiveness evaluation
  still requires consented real-world testing.
- Voiceprint recognition is experimental and should not be treated as final
  identity proof.
- Mental-health screening summaries are self-report screening aids only and do
  not constitute diagnosis.
- The system is not a medical diagnostic tool, legal evidence system, household
  surveillance tool, or emergency response substitute.

## Suggested First Contributions

- Docker deployment.
- Windows compatibility notes and test coverage.
- Additional intervention prompt templates.
- More privacy-preserving evaluation fixtures.

## 中文摘要

这是语言暴力干预系统的首个 alpha 版本。项目定位为隐私优先的端侧 AI 样机，用于识别高风险沟通、播放温和提醒、记录事件并支持人工复盘。系统不是医疗诊断、法律证据或紧急救援替代系统。

# Roadmap

Language Violence Intervention System is currently an alpha-stage edge AI
prototype. The roadmap below focuses on safer deployment, easier evaluation,
and clearer community contribution paths.

## v0.1.x Alpha Hardening

- Document real Raspberry Pi 5 deployment checks with microphone and speaker
  diagnostics.
- Add a Docker or containerized demo path for local development.
- Improve Windows compatibility notes for audio devices, local ASR, and WebUI.
- Expand intervention prompt templates and allow scenario-specific prompt sets.
- Add more regression tests for WebUI settings, event export, and report
  rendering.

## v0.2.x Evaluation And Privacy

- Build an opt-in evaluation protocol for false positives, false negatives, and
  intervention timing.
- Add clearer consent and retention workflows for voiceprint registration and
  media-filter calibration.
- Provide sample anonymized datasets or synthetic fixtures for community
  testing without real household recordings.
- Add exportable privacy/audit checklists for local deployments.
- Improve local-only mode documentation for users who do not configure cloud
  APIs.

## v0.3.x Productization

- Add installable packages or device images for Raspberry Pi 5.
- Improve multi-device gateway support for ARM boards such as RK3588 and Jetson.
- Add optional local notification integrations while preserving local-first
  privacy.
- Explore multilingual rule sets and prompt templates.
- Prepare a more complete demo video and public evaluation report.

## Contribution Ideas

- `Help wanted: Docker deployment`
- `Help wanted: Windows compatibility`
- `Good first issue: Add more intervention prompt templates`

## Boundaries

This roadmap does not change the project positioning. The system is an
assistive signal for observation, reminders, and human review. It is not a
medical diagnostic tool, legal evidence system, household surveillance tool, or
emergency response substitute.

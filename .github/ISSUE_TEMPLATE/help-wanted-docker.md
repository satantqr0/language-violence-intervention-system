---
name: "Help wanted: Docker deployment"
about: "Help package a local demo/runtime path with Docker or containers."
title: "Help wanted: Docker deployment"
labels: help wanted
assignees: ""
---

## Goal

Add a Docker or containerized development/demo path for the WebUI and local
runtime where feasible.

## Suggested Scope

- Document supported host platforms and audio-device limitations.
- Provide a minimal WebUI demo container using anonymous sample data.
- Keep `.env`, audio files, logs, voiceprints, profiles, and screening records
  outside the image.
- Avoid bundling model weights unless their licenses and download flow are
  clear.

## Acceptance Notes

- The setup should not require real household recordings.
- The documentation must keep the project boundary: assistive signal, human
  review, non-diagnostic, non-legal-evidence, and non-emergency substitute.

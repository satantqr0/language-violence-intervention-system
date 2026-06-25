# Open-Source Patent Review Checklist

This checklist is a practical publication review tool for this repository. It is
not legal advice and does not replace review by a patent agent or lawyer.

## Known Application Status

- Related Chinese invention patent application: 202610669466.3
- Title: 端侧语音识别混合语义分析语言暴力检测与主动干预系统
- Applicant: 童秋然
- Filing date: 2026-05-15
- Preliminary examination qualified notice date: 2026-06-25
- Current repository posture: public prototype source release, not the patent
  application file.

The application is pending. Do not describe it as an issued or granted patent
unless an authorization decision and patent certificate have actually been
received.

## Before Publishing A Release

Review every public release, README update, screenshot, issue template, demo,
blog post, and social post against this list:

- The release does not include patent application documents, claims,
  specification drafts, drawings, office-action correspondence, agency
  correspondence, or fee/filing records.
- Newly added technical content was either already supported by the filed
  application materials or has been intentionally approved for public
  open-source release.
- New detection algorithms, acoustic filters, voiceprint logic, speaker-profile
  logic, psychological-screening logic, active-intervention hardware,
  deployment topology, evaluation methods, and hardware designs have been
  checked for unfiled invention risk before publication.
- Apache License 2.0, `NOTICE`, `LEGAL_NOTICE.md`, and `PATENT_NOTICE.md` are
  present and linked from the README files.
- The release does not imply patent grant, medical certification, legal-evidence
  validity, emergency-response reliability, clinical diagnosis capability, or
  official endorsement by any third party.
- The release does not include real household recordings, transcripts,
  voiceprint templates, event logs, speaker profiles, screening results,
  safety-case records, deployment addresses, credentials, tokens, API keys, SSH
  keys, private certificates, or private runtime logs.
- Screenshots and demos use synthetic or anonymized data and do not expose
  private names, addresses, device identifiers, or family details.
- Third-party dependencies, models, icons, screenshots, media, and hardware
  descriptions are compatible with their own licenses and terms.
- `python3 scripts/patent_publication_guard.py` passes locally. The same guard
  also runs in GitHub Actions for pushes and pull requests.

## Safe-To-Publish Examples

- High-level project positioning and safety boundaries.
- Source code intentionally released under Apache License 2.0.
- Example configuration with empty placeholders.
- Anonymous screenshots and synthetic demo flows.
- General Raspberry Pi and ARM-device deployment notes.
- Publicly available third-party dependency references and license summaries.

## Review-Required Examples

- Detailed new algorithms or calibration methods not known to be in the filed
  patent application materials.
- New hardware structures, board layouts, acoustic enclosure designs, or
  production BOMs.
- Benchmark results from real household deployments.
- Model weights, proprietary prompt libraries, evaluation datasets, or
  unpublished tuning parameters.
- Contributions from outside parties that include invention claims, private
  implementation notes, or unverified third-party code.

## Do-Not-Publish Examples

- The patent application text, claims, specification drawings, draft amendments,
  examination opinions, or agent correspondence before they are officially
  published or cleared.
- Any real audio, raw transcripts, voiceprint embeddings, profile records,
  mental-health screening answers, safety-case notes, or private logs.
- Passwords, API keys, GitHub tokens, SSH private keys, sudo passwords, cloud
  credentials, private TLS keys, or private deployment addresses.
- Statements that the patent has been granted before grant, or that the system
  is suitable for diagnosis, legal proof, emergency rescue, or coercive
  monitoring.

## Maintainer Notes

For substantial changes, keep a short private record of why the content was
published and whether it was already covered by the filed application or
intentionally released as open-source material. Do not store private patent
strategy notes in this public repository.

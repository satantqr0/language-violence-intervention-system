#!/usr/bin/env python3
"""Guard public repository updates against patent and privacy disclosure slips."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_PATENT_NOTICE_FILES = {
    "README.md",
    "README_EN.md",
    "LEGAL_NOTICE.md",
    "NOTICE",
    "PATENT_NOTICE.md",
    "OPEN_SOURCE_PATENT_REVIEW.md",
    "scripts/patent_publication_guard.py",
}

ALLOWED_EMPTY_PLACEHOLDERS = {
    "data/.gitkeep",
    "logs/.gitkeep",
}

BLOCKED_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".aac",
    ".jsonl",
    ".sqlite",
    ".sqlite3",
    ".db",
}

BLOCKED_PATH_PATTERNS = [
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)audio/"),
    re.compile(r"(^|/)models/.+"),
]

SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:OPENSSH|RSA|DSA|EC|PRIVATE) PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

SECRET_ASSIGNMENT = re.compile(
    r"(?m)^[ \t]*(DASHSCOPE_API_KEY|VD_WEB_PASSWORD|SSHPASS|SUDO_PASSWORD)[ \t]*=[ \t]*['\"]?([^'\"\s#]+)"
)

PLACEHOLDER_WORDS = (
    "your",
    "example",
    "change",
    "strong",
    "password",
    "sudo",
    "placeholder",
    "请",
    "你的",
    "设置",
)

PATENT_PROSECUTION_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        "权利要求书",
        "说明书附图",
        "说明书摘要",
        "审查意见",
        "审查员",
        "代理事务所",
        "国家知识产权局",
        "专利局",
        "受理通知书",
        "初步审查合格通知书",
        "office[- ]action",
        "patent claims draft",
        "claim chart",
        "prosecution history",
    ]
]

GRANT_MISSTATEMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        "已授权专利",
        "授权发明专利",
        "已获授权",
        "issued patent",
    ]
]


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [ROOT / line for line in output.splitlines() if line.strip()]
    except Exception:
        files: list[Path] = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or not path.is_file():
                continue
            files.append(path)
        return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    if len(data) > 2_000_000:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    if not value or value.startswith("$"):
        return True
    return any(word in lowered for word in PLACEHOLDER_WORDS)


def main() -> int:
    problems: list[str] = []

    for path in tracked_files():
        name = rel(path)
        if name in ALLOWED_EMPTY_PLACEHOLDERS:
            continue

        if path.suffix.lower() in BLOCKED_SUFFIXES:
            problems.append(f"{name}: blocked public file type {path.suffix}")

        for pattern in BLOCKED_PATH_PATTERNS:
            if pattern.search(name):
                problems.append(f"{name}: blocked public data/secret path")

        text = read_text(path)
        if text is None:
            continue

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: possible secret or private key content")
                break

        for match in SECRET_ASSIGNMENT.finditer(text):
            value = match.group(2).strip()
            if value and not looks_like_placeholder(value):
                problems.append(f"{name}: possible non-placeholder {match.group(1)} value")
                break

        if name not in ALLOWED_PATENT_NOTICE_FILES:
            for pattern in PATENT_PROSECUTION_PATTERNS:
                if pattern.search(text):
                    problems.append(f"{name}: possible patent prosecution material term `{pattern.pattern}`")
                    break

        if name not in ALLOWED_PATENT_NOTICE_FILES:
            for pattern in GRANT_MISSTATEMENT_PATTERNS:
                if pattern.search(text):
                    problems.append(f"{name}: possible patent grant misstatement `{pattern.pattern}`")
                    break

    if problems:
        print("Patent/publication guard failed. Review before public release:\n")
        for item in problems:
            print(f"- {item}")
        return 1

    print("Patent/publication guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

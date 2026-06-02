#!/usr/bin/env python3
"""Compatibility wrapper for the secured Raspberry Pi deployment script."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    deploy_script = Path(__file__).with_name("deploy.sh")
    return subprocess.call(["bash", str(deploy_script), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())

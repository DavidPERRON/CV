#!/usr/bin/env python3
"""Thin wrapper around cv_agent.cli.generate_main."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cv_agent.cli import generate_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(generate_main(sys.argv[1:]))

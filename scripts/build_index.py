#!/usr/bin/env python3
"""Regenerate runs/index.html from all existing run directories.

Usage:
    python3 scripts/build_index.py
    python3 scripts/build_index.py --runs-dir /path/to/runs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cv_agent.render.index_html import write_index  # noqa: E402
from cv_agent.settings import RUNS_DIR  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate runs/index.html")
    ap.add_argument("--runs-dir", default=None,
                    help="Path to the runs/ directory (default: repo runs/)")
    args = ap.parse_args(argv)
    runs_dir = Path(args.runs_dir) if args.runs_dir else RUNS_DIR
    if not runs_dir.exists():
        print(f"ERROR: runs directory not found: {runs_dir}", file=sys.stderr)
        return 1
    out = write_index(runs_dir)
    print(f"Index written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

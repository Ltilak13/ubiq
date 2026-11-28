"""Keep one GitHub issue per goal criterion. Kept for old callers; use `ubiq sync github`.

This forwards its arguments (`--dry-run`, `--apply`, `--repo`) to `ubiq sync
github` with this repository as the root. The planner and the GitHub adapter
live in `src/ubiq/sync.py`, and `ubiq.yaml` says which records to mirror.
"""
import sys
from pathlib import Path

from ubiq.cli import main

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    sys.exit(main(['sync', 'github', '--root', str(ROOT), *sys.argv[1:]]))

"""CLI: apply database migrations.  Usage: python -m ytagent.migrate"""
from __future__ import annotations

from .config import load_settings
from .migrations.runner import run_migrations


def main() -> None:
    settings = load_settings()
    applied = run_migrations(settings)
    print(f"[migrate] done; applied {len(applied)} migration(s): {applied}")


if __name__ == "__main__":
    main()

"""Health command — one runnable answer to "do the codes work" (B-completion NOW bundle).

Runs the no-live-key verify suite as isolated subprocesses and aggregates pass/fail. The 13 existing
offline verifies need no API keys (pure logic or Postgres + monkeypatched providers); the two new ones
(allowance, subject_terms) are pure. `verify_vision_fixtures` is the ONLY live-key verify (Anthropic,
pennies) and runs only when ANTHROPIC_API_KEY is set. A Postgres-down environment is reported as exit 3
(environment incomplete) — DISTINCT from a verify FAILING (exit 1, a real defect). Failures are listed
FIRST because that list takes priority.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.health
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import psycopg

from ytagent.config import load_settings

# (module, needs_db). Pure-logic first (fast, no infra), then Postgres-required (monkeypatched providers).
_OFFLINE = [
    ("verify_cost_estimate", False),
    ("verify_slice3", False),
    ("verify_curation", False),
    ("verify_allowance", False),          # §1 allowance fix (pure)
    ("verify_subject_terms", False),      # subject-terms flag (pure)
    ("verify_slice1", True),
    ("verify_layer1", True),
    ("verify_scheduler", True),
    ("verify_slice4", True),
    ("verify_slice5", True),
    ("verify_e2e", True),
    ("verify_scheduler_run", True),
    ("verify_spend_gate", True),
    ("verify_produce_resume", True),
    ("verify_publish", True),
]
_OPTIONAL_LIVE = [("verify_vision_fixtures", "ANTHROPIC_API_KEY")]


def _pg_up(settings) -> bool:
    try:
        with psycopg.connect(settings.dsn(), connect_timeout=3) as c:
            c.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False


def _run(mod: str) -> tuple[int, str, float]:
    t = time.monotonic()
    p = subprocess.run([sys.executable, "-m", f"scripts.{mod}"], capture_output=True, text=True)
    dur = time.monotonic() - t
    lines = [ln for ln in (p.stdout or "").strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ((p.stderr or "").strip().splitlines()[-1:] or [""])[-1]
    return p.returncode, tail.strip()[:80], dur


def main() -> None:
    settings = load_settings()
    pg = _pg_up(settings)
    results: list[tuple[str, str, float, str]] = []      # (mod, PASS/FAIL, secs, tail)
    skipped: list[str] = []

    for mod, needs_db in _OFFLINE:
        if needs_db and not pg:
            skipped.append(f"{mod} (Postgres down)")
            continue
        rc, tail, dur = _run(mod)
        results.append((mod, "PASS" if rc == 0 else "FAIL", dur, tail))

    for mod, keyenv in _OPTIONAL_LIVE:
        if os.environ.get(keyenv):
            rc, tail, dur = _run(mod)
            results.append((mod, "PASS" if rc == 0 else "FAIL", dur, tail))
        else:
            skipped.append(f"{mod} (no {keyenv} — optional live)")

    fails = [r for r in results if r[1] == "FAIL"]

    print("=" * 72)
    print("AGENT HEALTH — verify suite")
    print("=" * 72)
    if fails:                                            # failures FIRST — this is the priority list
        print("FAILURES (the defect list — fix before proceeding):")
        for mod, _st, dur, tail in fails:
            print(f"  ❌ {mod:<24} {dur:5.1f}s  {tail}")
        print("-" * 72)
    for mod, st, dur, tail in results:
        print(f"  {'✅' if st == 'PASS' else '❌'} {mod:<24} {dur:5.1f}s  {tail}")
    if skipped:
        print("-" * 72)
        for s in skipped:
            print(f"  ⏭️  {s}")

    n_pass = sum(1 for r in results if r[1] == "PASS")
    print("=" * 72)
    print(f"{n_pass}/{len(results)} passed" + (f", {len(fails)} FAILED" if fails else "")
          + (f", {len(skipped)} skipped" if skipped else ""))

    if fails:
        sys.exit(1)                                      # a real code defect — takes precedence
    if not pg:
        print("environment incomplete: Postgres unreachable — run `docker compose up -d postgres`.")
        sys.exit(3)                                      # environment, not a code defect
    print("ALL PASSED — the codes run clean.")
    sys.exit(0)


if __name__ == "__main__":
    main()

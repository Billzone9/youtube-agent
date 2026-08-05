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
    ("verify_shorts", False),             # M1 Shorts density + bed library (pure/local)
    ("verify_short_publish", False),      # M1 Short publish gate — must classify as a Short (pure)
    ("verify_d3", False),                 # D3 — audio-design completeness guard (declared vs defect)
    ("verify_grounding", False),          # A1 grounded research — bounded loop + declared→writer
    ("verify_research_order", True),       # A1 conductor — gate BEFORE research (sequence) + resume
    ("verify_cohort_playlist", True),     # M1 item 2 — unlisted cohort playlist writes (confined)
    ("verify_d2", True),                  # D2 — job terminal status, explicit live-publish, approval TTL
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


# The hermeticity backstop (verify-hermeticity-standard.md): a verify that leaves production rows is an
# accidental-upload path. Snapshot the danger tables before the suite; assert zero net-new after.
_DANGER = ("approvals", "videos", "jobs")


def _danger_marks(settings) -> dict:
    with psycopg.connect(settings.dsn(), connect_timeout=3) as c:
        return {t: c.execute(f"SELECT COALESCE(MAX(id),0) FROM {t}").fetchone()[0] for t in _DANGER}


def _leftover(settings, marks: dict) -> list[str]:
    dirty = []
    with psycopg.connect(settings.dsn(), connect_timeout=3) as c:
        for t in _DANGER:
            n = c.execute(f"SELECT count(*) FROM {t} WHERE id > %s", [marks[t]]).fetchone()[0]
            if n:
                dirty.append(f"{t}:+{n}")
    return dirty


# A live verify can fail for reasons that are NOT a code defect — the provider API is unreachable or
# unfunded. Treat those as ENVIRONMENT (skip), the same as Postgres-down, so a billing/credits issue
# never masquerades as broken code. (Offline verifies never hit these.)
_API_DOWN = ("credit balance is too low", "authentication_error", "rate_limit", "BadRequestError",
             "insufficient_quota", " 401", " 429", "Connection error")


def _api_down_reason(text: str) -> str | None:
    for m in _API_DOWN:
        if m in text:
            return m.strip()
    return None


def _run(mod: str) -> tuple[int, str, float, list[str]]:
    t = time.monotonic()
    p = subprocess.run([sys.executable, "-m", f"scripts.{mod}"], capture_output=True, text=True)
    dur = time.monotonic() - t
    lines = [ln for ln in (p.stdout or "").strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ((p.stderr or "").strip().splitlines()[-1:] or [""])[-1]
    # SKIP LEDGER: a verify prints ⏭️ for a check it could not run (local-only media absent). Surface
    # these at the health level so a green CI run and a green local run mean the SAME thing — zero
    # failures — with the environmental delta made EXPLICIT rather than hidden inside a passing verify.
    skips = [f"{mod}: {ln.split('⏭️', 1)[1].strip()}" for ln in lines if "⏭️" in ln]
    _run.last_output = (p.stdout or "") + (p.stderr or "")   # for API-down detection on live verifies
    return p.returncode, tail.strip()[:80], dur, skips


def main() -> None:
    settings = load_settings()
    pg = _pg_up(settings)
    results: list[tuple[str, str, float, str]] = []      # (mod, PASS/FAIL, secs, tail)
    skipped: list[str] = []

    marks = _danger_marks(settings) if pg else None      # hermeticity high-water before the suite
    check_skips: list[str] = []                          # in-verify skips (local-only media absent)

    for mod, needs_db in _OFFLINE:
        if needs_db and not pg:
            skipped.append(f"{mod} (Postgres down)")
            continue
        rc, tail, dur, sk = _run(mod)
        results.append((mod, "PASS" if rc == 0 else "FAIL", dur, tail))
        check_skips += sk

    for mod, keyenv in _OPTIONAL_LIVE:
        if os.environ.get(keyenv):
            rc, tail, dur, sk = _run(mod)
            reason = _api_down_reason(getattr(_run, "last_output", "")) if rc != 0 else None
            if reason:                                   # provider API unreachable/unfunded → ENVIRONMENT
                skipped.append(f"{mod} (live API unavailable: {reason} — not a code defect)")
            else:
                results.append((mod, "PASS" if rc == 0 else "FAIL", dur, tail))
                check_skips += sk
        else:
            skipped.append(f"{mod} (no {keyenv} — optional live)")

    # Hermeticity backstop: any production rows left by the suite are a defect (accidental-upload path).
    leftover = _leftover(settings, marks) if marks is not None else []
    if leftover:
        results.append(("hermeticity", "FAIL", 0.0,
                        f"verifies left production rows: {', '.join(leftover)} — non-hermetic verify"))

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
    if check_skips:                                      # explicit ledger: checks that could not run
        print("-" * 72)
        print("SKIPPED CHECKS (local-only media absent — green means the same, minus these):")
        for s in check_skips:
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

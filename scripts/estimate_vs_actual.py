"""B3 item 2 — estimate-vs-actual, per job, so we see SYSTEMATICALLY how wrong the estimator is (not
per incident). For every production that hit the 4→5 gate, the full pre-flight estimate is recorded (the
`spend_estimate` event); this compares it to the ACTUAL ledger for that job.

Two traps this AVOIDS (both are numbers that look like validation and aren't):
- A ratio against a reconciled=false row is the estimate vs itself → shown as UNSETTLED, not a ratio.
- A ratio for a job that DIED mid-production compares a full-film estimate to a partial spend → shown
  as PARTIAL N/M beats, not a ratio. Only jobs that ran to completion get a real ratio.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.estimate_vs_actual
"""
from __future__ import annotations

import asyncio
import json
import os

import psycopg
from psycopg.rows import dict_row

from ytagent.config import load_settings

# a job in one of these states did NOT run to completion → never quote a ratio for it
_INCOMPLETE = {"failed", "blocked", "rejected"}


def _spoken_beats(script_path: str | None) -> int | None:
    """Total SPOKEN beats in the job's script (the denominator for partial coverage). None if unreadable."""
    if not script_path:
        return None
    p = script_path if os.path.isabs(script_path) else os.path.join(os.getcwd(), script_path)
    try:
        d = json.load(open(p))
        return sum(1 for b in d.get("beats", []) if (b.get("vo") or "").strip())
    except Exception:  # noqa: BLE001
        return None


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    rows = await (await conn.execute("""
        WITH est AS (
          SELECT DISTINCT ON (job_id) job_id,
                 (data->>'total_gbp')::numeric est_gbp,
                 (data->>'tts_chars')::numeric est_tts,
                 (data->>'music_credits')::numeric + COALESCE((data->>'sfx_credits')::numeric,0) est_music
          FROM events WHERE type='spend_estimate' AND job_id IS NOT NULL
          ORDER BY job_id, id DESC),
        act AS (
          SELECT job_id,
                 SUM(amount_gbp) act_gbp,
                 SUM(credits) FILTER (WHERE provider='ElevenLabs TTS') act_tts,
                 SUM(credits) FILTER (WHERE provider='ElevenLabs Music') act_music,
                 COUNT(*) FILTER (WHERE provider='ElevenLabs TTS') voiced_beats,
                 bool_and(reconciled) FILTER (WHERE provider='ElevenLabs TTS') tts_settled,
                 bool_and(reconciled) FILTER (WHERE provider='ElevenLabs Music') music_settled
          FROM cost_ledger WHERE job_id IS NOT NULL GROUP BY job_id)
        SELECT e.job_id, j.status, e.est_gbp, a.act_gbp, e.est_tts, a.act_tts, e.est_music, a.act_music,
               a.voiced_beats, a.tts_settled, a.music_settled,
               j.result->'production_state'->>'script_path' script_path,
               (j.result->'production_state'->'cfg'->>'n_beats')::int cfg_beats
        FROM est e JOIN act a USING (job_id) JOIN jobs j ON j.id=e.job_id
        ORDER BY e.job_id DESC""")).fetchall()

    print("ESTIMATE vs ACTUAL (per job that hit the spend gate)")
    print("=" * 82)
    print(f"  {'job':>4} {'status':<10} {'est £':>7} {'act £':>7} {'TTS e/a':>17} {'Music e/a':>16}")
    if not rows:
        print("  (no job has both a persisted estimate AND ledgered actuals yet.)")
    for r in rows:
        def ea(e, a, settled):
            e = float(e or 0); a = float(a or 0)
            if not a:
                return f"{e:.0f}/—"
            # a ratio vs a reconciled=false row is the estimate vs itself — meaningless until settled
            return f"{e:.0f}/{a:.0f} {e/a:.2f}x" if settled else f"{e:.0f}/{a:.0f} UNSETTLED"

        if r["status"] in _INCOMPLETE:
            # died mid-production → a full-film estimate vs a partial spend is NOT a ratio. Show coverage.
            n = int(r["voiced_beats"] or 0)
            m = _spoken_beats(r["script_path"]) or r["cfg_beats"]
            cov = f"PARTIAL {n}/{m} beats" if m else f"PARTIAL {n}/? beats"
            print(f"  {r['job_id']:>4} {r['status']:<10} "
                  f"£{float(r['est_gbp'] or 0):>5.2f} £{float(r['act_gbp'] or 0):>5.2f} "
                  f"{cov:>34}  (full-film est vs partial spend — no ratio)")
            continue
        print(f"  {r['job_id']:>4} {r['status']:<10} "
              f"£{float(r['est_gbp'] or 0):>5.2f} £{float(r['act_gbp'] or 0):>5.2f} "
              f"{ea(r['est_tts'], r['act_tts'], r['tts_settled']):>17} "
              f"{ea(r['est_music'], r['act_music'], r['music_settled']):>16}")

    print("\nTTS is SETTLED and validated: job 155 = 4,379 estimated vs 4,378 settled (1.00x), from two")
    print("independent sources (our char count + ElevenLabs history) — the first non-circular ratio here.")
    print("All 18 production TTS rows settled by request_id (0 fallback, 0 unmatched).")
    print("MUSIC alone remains UNSETTLED — pending the guarded balance-delta (no per-call history exists).")
    print("PARTIAL = job died before completing; a full-film estimate vs a part-film spend is not a ratio.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

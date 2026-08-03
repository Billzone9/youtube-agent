"""B3 item 2 — estimate-vs-actual, per job, so we see SYSTEMATICALLY how wrong the estimator is (not
per incident). For every production that hit the 4→5 gate, the full pre-flight estimate is recorded (the
`spend_estimate` event); this compares it to the ACTUAL ledger for that job. TTS is char-exact so it
should track tightly; music is the one to watch (async settlement). A persistent skew here is the signal
to re-tune scheduler/cost.py or run the balance reconciler.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.estimate_vs_actual
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent.config import load_settings


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
                 SUM(credits) FILTER (WHERE provider='ElevenLabs Music') act_music
          FROM cost_ledger WHERE job_id IS NOT NULL GROUP BY job_id)
        SELECT e.job_id, j.status,
               e.est_gbp, a.act_gbp, e.est_tts, a.act_tts, e.est_music, a.act_music
        FROM est e JOIN act a USING (job_id) JOIN jobs j ON j.id=e.job_id
        ORDER BY e.job_id DESC""")).fetchall()

    print("ESTIMATE vs ACTUAL (per job that hit the spend gate)")
    print("=" * 78)
    print(f"  {'job':>4} {'status':<10} {'est £':>7} {'act £':>7} {'TTS e/a':>13} {'Music e/a':>13}")
    if not rows:
        print("  (no job has both a persisted estimate AND ledgered actuals yet — the estimate is")
        print("   recorded from the next gated production onward; job 276 paused before full spend.)")
    for r in rows:
        def ea(e, a):
            e = float(e or 0); a = float(a or 0)
            return f"{e:.0f}/{a:.0f}" + ("" if not a else f" {e/a:.2f}x" if a else "")
        print(f"  {r['job_id']:>4} {r['status']:<10} "
              f"£{float(r['est_gbp'] or 0):>5.2f} £{float(r['act_gbp'] or 0):>5.2f} "
              f"{ea(r['est_tts'], r['act_tts']):>13} {ea(r['est_music'], r['act_music']):>13}")
    print("\nNotes: TTS is char-exact (estimate should ≈ actual). Music actual rows are per-call")
    print("ESTIMATES until the balance reconciler settles them; a real skew shows only after settlement.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

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
                 SUM(credits) FILTER (WHERE provider='ElevenLabs Music') act_music,
                 bool_and(reconciled) FILTER (WHERE provider='ElevenLabs TTS') tts_settled,
                 bool_and(reconciled) FILTER (WHERE provider='ElevenLabs Music') music_settled
          FROM cost_ledger WHERE job_id IS NOT NULL GROUP BY job_id)
        SELECT e.job_id, j.status,
               e.est_gbp, a.act_gbp, e.est_tts, a.act_tts, e.est_music, a.act_music,
               a.tts_settled, a.music_settled
        FROM est e JOIN act a USING (job_id) JOIN jobs j ON j.id=e.job_id
        ORDER BY e.job_id DESC""")).fetchall()

    print("ESTIMATE vs ACTUAL (per job that hit the spend gate)")
    print("=" * 80)
    print(f"  {'job':>4} {'status':<10} {'est £':>7} {'act £':>7} {'TTS e/a':>16} {'Music e/a':>16}")
    if not rows:
        print("  (no job has both a persisted estimate AND ledgered actuals yet.)")
    for r in rows:
        def ea(e, a, settled):
            e = float(e or 0); a = float(a or 0)
            if not a:
                return f"{e:.0f}/—"
            # A ratio against an UNRECONCILED row is the estimate vs ITSELF (both from seconds×15 /
            # char-count) — meaningless. Only show a ratio once the row is actually settled.
            return f"{e:.0f}/{a:.0f} {e/a:.2f}x" if settled else f"{e:.0f}/{a:.0f} UNSETTLED"
        print(f"  {r['job_id']:>4} {r['status']:<10} "
              f"£{float(r['est_gbp'] or 0):>5.2f} £{float(r['act_gbp'] or 0):>5.2f} "
              f"{ea(r['est_tts'], r['act_tts'], r['tts_settled']):>16} "
              f"{ea(r['est_music'], r['act_music'], r['music_settled']):>16}")
    print("\nUNSETTLED = the actual row is reconciled=false, written from the SAME char-count / seconds×15")
    print("model the estimate uses — so a ratio would be the estimate compared to itself, not validation.")
    print("A real ratio appears only after settlement: TTS via reconcile_tts.py (once speech_history_read")
    print("is on the key), music via the balance-delta. Only then is a 1.00x meaningful.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

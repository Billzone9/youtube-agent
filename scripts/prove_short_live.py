"""LIVE runner over the REAL conductor `produce.produce_short` — one credit-light Short end to end to the
Telegram card (dry-run; a tap cannot upload). Thin: all logic lives in produce_short now. Inside the
credit window (reused bed = 0, no TTS; the cost is the vision).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_short_live
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing import get_stock_providers
from scripts.supervised_tick import _make_notifier

_SUBJECT = "african elephant"
_BRIEF = "a wild African elephant moving slowly across the open savanna, close, cinematic, daytime"


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        raise SystemExit(f"prereqs — llm={bool(llm)} providers={len(providers)}")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    notifier, bot = await _make_notifier(settings)

    res = await produce.produce_short(
        conn, notifier, channel=ch, subject=_SUBJECT, brief=_BRIEF, providers=providers,
        llm_provider=llm, usage_sink=sink, publisher=DryRunPublisher(), chat_id=settings.chat_id,
        duration_s=20, n_target=3)

    m, r = res["result"].qc, res["result"]
    total = await (await conn.execute(
        "SELECT COALESCE(SUM(amount_gbp),0) g FROM cost_ledger WHERE job_id=%s", [res["job_id"]])).fetchone()
    print(f"\n✅ SHORT job {res['job_id']} ON THE CARD (dry-run). approval {res['submit']['approval']['id']}.")
    print(f"   {m.get('width')}x{m.get('height')} {m.get('duration_s')}s | {m.get('loudness_lufs')} LUFS | "
          f"noise gate {'PASS' if r.noise_gate.ok else 'FAIL'} | {res['clips']} clips")
    print(f"   estimate £{res['estimate_gbp']:.3f} vs actual £{float(total['g']):.4f} "
          f"(vision-dominant; ElevenLabs £0 — reused bed, no TTS)")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

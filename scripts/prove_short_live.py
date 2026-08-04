"""LIVE integration proof — one credit-light Short through the WHOLE path as ONE run:
source_clips_for_brief → pick_bed → bind_short_spec → assemble_spec → generate_description → submit to
the Telegram card. DRY-RUN publish (a tap cannot upload). Reports the master QC (noise hi-bands + LUFS)
and the ACTUAL vision spend. Inside the ~5,684-credit window (bed reused = 0, no TTS, vision ~£0.05–0.10).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_short_live
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import repo
from ytagent.assembly import assemble_spec, qc
from ytagent.assembly.beds import pick_bed
from ytagent.assembly.binder import bind_short_spec
from ytagent.config import load_settings
from ytagent.metadata.description import generate_description
from ytagent.metadata.llm_writer import LLMWriter
from ytagent.metadata.research import UnavailableResearch
from ytagent.orchestrator import submit_video_for_approval
from ytagent.produce import _drain_llm
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing import NoMatch, get_stock_providers, source_clips_for_brief
from scripts.supervised_tick import _make_notifier

_SUBJECT = "african elephant"
_BRIEF = "a wild African elephant moving slowly across the open savanna, close, cinematic, daytime"
_DUR = 20


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        raise SystemExit(f"prereqs — llm={bool(llm)} providers={len(providers)}")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    bed = pick_bed(0)
    if bed is None:
        raise SystemExit("no attested bed — seed assets/beds/ + beds-manifest.json")

    # a real produce job (format=short) so vision spend attributes to it (note 1)
    job = await (await conn.execute(
        "INSERT INTO jobs (channel_id, type, status, stage, payload) "
        "VALUES (%s,'produce','assembling','sourced',%s) RETURNING *",
        [ch["id"], Jsonb({"topic": _SUBJECT, "format": "short"})])).fetchone()
    print(f"=== LIVE SHORT — job {job['id']} — subject '{_SUBJECT}', {_DUR}s 9:16, bed {os.path.basename(bed)} ===")

    used = await repo.sourcing.used_asset_ids(conn, ch["id"])
    print(f"cross-video exclude: {len(used)} clips already used by this channel\n")
    pricing = await repo.ledger.get_llm_pricing(conn)

    verdicts = []
    print("[1] SOURCE (single-beat, bounded vision) …")
    got = await source_clips_for_brief(
        conn, providers, brief=_BRIEF, brief_ref="short-1", approx_seconds=_DUR, target_fmt="9:16",
        target_w=1080, target_h=1920, cache_dir="assets/sourced", channel_id=ch["id"], job_id=job["id"],
        llm=llm, n_target=3, n_min=1, exclude_ids=used, vision=True, subject=_SUBJECT,
        collect_verdicts=verdicts)
    vision_gbp = await _drain_llm(conn, sink, pricing, channel_id=ch["id"], job_id=job["id"])
    if isinstance(got, NoMatch):
        print(f"   NoMatch — {got.reason}. Vision spent £{vision_gbp:.4f} on {len(verdicts)} checks.")
        await conn.close()
        return
    print(f"   {len(got)} clip(s) sourced; {len(verdicts)} vision checks; vision spend £{vision_gbp:.4f}")

    print("[2] BIND + ASSEMBLE (short density + noise + LUFS gates) …")
    spec = bind_short_spec(got, bed=bed, duration_s=_DUR, title=f"{_SUBJECT} short").for_format("9:16")
    wd = tempfile.mkdtemp(prefix="short-live-")
    dst = os.path.join(wd, "short.mp4")
    result = await asyncio.to_thread(assemble_spec, spec, dst=dst, provenance_ref="sourced_assets", workdir=wd)
    m, n = result.qc, qc.noise_report(dst)
    print(f"   {m.get('width')}x{m.get('height')} {m.get('duration_s')}s | {m.get('loudness_lufs')} LUFS "
          f"peak {m.get('peak_dbfs')} dBFS")
    print(f"   NOISE: hi8k={n['hi8k_db']} hi10k={n['hi10k_db']} hi16k={n['hi16k_db']} | "
          f"gate={'PASS' if result.noise_gate.ok else 'FAIL'}")

    print("[3] DESCRIBE + SUBMIT to the Telegram card (dry-run) …")
    notifier, bot = await _make_notifier(settings)
    desc = generate_description({"topic": _SUBJECT, "title": f"Wild {_SUBJECT.title()}", "facts": "",
                                 "contents": None}, ch, UnavailableResearch(), LLMWriter(llm))
    await _drain_llm(conn, sink, pricing, channel_id=ch["id"], job_id=job["id"])
    # metadata_source is WHO authored the text (research_writer — an allowed value); the SHORT/format
    # distinction lives on the job payload (format=short), not here (video_metadata.source is constrained).
    sub = await submit_video_for_approval(
        conn, notifier, channel=ch, video_meta=result.qc, description=desc, chat_id=settings.chat_id,
        publish_mode=DryRunPublisher().mode, metadata_source="research_writer")
    total = await (await conn.execute(
        "SELECT COALESCE(SUM(amount_gbp),0) g FROM cost_ledger WHERE job_id=%s", [job["id"]])).fetchone()
    print(f"\n✅ SHORT ON THE CARD (dry-run, not tapped). approval {sub['approval']['id']}.")
    print(f"   Short job {job['id']} ledgered spend: £{float(total['g']):.4f} "
          f"(ElevenLabs £0 — reused bed, no TTS; the cost IS the vision).")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

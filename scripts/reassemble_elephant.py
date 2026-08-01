"""Re-assemble the elephant film REUSING the already-generated TTS + music cues + bed on disk (the
first live run generated them, spending 2475 music credits, then crashed in a logging line BEFORE the
render). This path spends NO new TTS/Music credits — it binds the existing narration + audio design,
runs the density + noise gates, authors the description, and submits for Telegram approval (dry-run).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.reassemble_elephant
"""
from __future__ import annotations

import asyncio
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.audio_design import AudioDesign, plan_cues
from ytagent.assembly.spec import MusicCue
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.events import record_event
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from scripts.produce_elephant import _WORKDIR, _DST, _load_script, _reconstruct, _make_notifier

_AUDIO = os.path.join(_WORKDIR, "audio")
_CUE_FILES = {"theme": "cue_theme.mp3", "journey": "cue_journey.mp3", "resolution": "cue_resolution.mp3"}


def _rebuild_design(script, channel) -> AudioDesign:
    cue_specs, breathers, _ = plan_cues(script, channel)
    d = AudioDesign(breathers=breathers)
    for spec in cue_specs:
        path = os.path.abspath(os.path.join(_AUDIO, _CUE_FILES[spec.key]))
        if not os.path.exists(path):
            continue
        for bidx in spec.beats:
            d.cues[bidx] = MusicCue(file=path, in_db=spec.in_db, fade_in=2.0, fade_out=3.0)
        d.layers.append(f"{spec.key} @{spec.in_db}dB → beats {list(spec.beats)}")
    bed = os.path.abspath(os.path.join(_AUDIO, "bed.mp3"))
    if os.path.exists(bed):
        d.bed = bed
        d.layers.append("bed (crossfade-looped, ~-30dB)")
    d.manifest = {"narration": "AI text-to-speech", "music": "AI-generated instrumental score",
                  "ambience": "AI-generated", "footage": "licensed / CC-0 stock"}
    return d


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    script = _load_script()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    pricing = await repo.ledger.get_llm_pricing(conn)
    sourced, missing = await _reconstruct(conn)
    if missing:
        print(f"ABORT — missing curated clips: {missing}")
        await conn.close(); raise SystemExit(2)

    # reuse the on-disk narration (spoken beats only; beat1 is wordless)
    narration = {}
    for b in script.beats:
        p = os.path.abspath(os.path.join(_WORKDIR, f"narr_beat{b.index}.mp3"))
        if os.path.exists(p):
            narration[b.index] = p
    design = _rebuild_design(script, ch)
    print(f"=== ELEPHANT — RE-ASSEMBLE (reusing on-disk audio, NO new spend) ===")
    print(f"clips {sum(len(v) for v in sourced.values())}/26 | narration {len(narration)} beats | "
          f"cues {len(design.cues)} beats scored | bed={'yes' if design.bed else 'no'} | "
          f"breathers {len(design.breathers)}")

    os.makedirs(os.path.dirname(os.path.abspath(_DST)), exist_ok=True)
    notifier, bot = await _make_notifier(settings)
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                     payload={"topic": "african elephant", "reassemble": True})
        await record_event(conn, "produce_started", message="elephant re-assemble (reuse audio)",
                           channel_id=ch["id"], job_id=job["id"])

    result = await produce._assemble_and_submit(
        conn, notifier, channel=ch, script=script, sourced=sourced, narration=narration,
        llm_provider=llm, usage_sink=sink, pricing=pricing, description_exemplar=None,
        publisher=DryRunPublisher(), chat_id=settings.chat_id, dst=_DST, workdir=_WORKDIR,
        job_id=job["id"], topic="african elephant", target_fmt="16:9", target_w=1920, target_h=1080,
        design=design)

    qc = result["result"].qc
    noise = result["result"].noise
    disclosure = (result["description"].description or "").strip().splitlines()[-1]
    print("\n=== MASTER QC (vs lion benchmark: 1080p/24fps, ~-14 LUFS, 48kHz, no clip, no hiss) ===")
    print(f"  resolution : {qc.get('width')}x{qc.get('height')} @ {qc.get('fps')}fps   (lion 1920x1080@24)")
    print(f"  duration   : {qc.get('duration_s')}s ({qc.get('duration_s',0)/60:.1f} min)   (lion 394s)")
    print(f"  loudness   : {qc.get('loudness_lufs')} LUFS   peak {qc.get('peak_dbfs')} dBFS   (target ~-14 / <0)")
    print(f"  noise floor: {qc.get('noise_floor_db')} dB")
    print(f"  audio      : {noise.get('sample_rate')} Hz   >16k={noise.get('hi16k_db')} dB   "
          f">8k={noise.get('hi8k_db')} dB   gate={'PASS' if result['result'].noise_gate.ok else 'FAIL'}")
    print(f"  audio layers: {'; '.join(design.layers)}")
    print(f"  disclosure : {disclosure}")
    bud = await budget_status(conn)
    print(f"\nSUBMITTED for approval (dry_run). month-to-date £{bud['month_spend_gbp']:.2f} "
          f"/ £{bud['ceiling_gbp']:.0f} ({bud['tier']}).")
    print(f"master: {result['result'].output_path}")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

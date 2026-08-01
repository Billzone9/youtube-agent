"""STAGE 2 — produce the elephant film 'The Old Paths' END TO END from the Stage-1 curated clips:
TTS the 6 spoken beats → design the audio (score cues + ambience bed, structural breathers, optional
SFX) → assemble (density + noise gates) → author the description (contents-manifest disclosure) →
submit for Telegram approval. The 26 curated clips are reconstructed from the DB (no re-sourcing, no
re-vision). Publish is a DRY RUN (the real upload is a separate gate on Banks's YES via the bot).

SPENDS: ElevenLabs TTS (~£3 of credits for 6 beats) + Music (cues+bed, ≤4000-credit hard ceiling).
Estimated + reported BEFORE generation. Run:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.produce_elephant
"""
from __future__ import annotations

import asyncio
import json
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.audio_design import _BED_S, _CREDITS_PER_SEC, plan_cues
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.music import MusicScopeError, get_music_provider
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing.base import Candidate, GateResult, SourcedAsset
from ytagent.sourcing.provenance import build_asset_provenance
from ytagent.tts import get_tts_provider

_SCRIPT = "assets/produced/elephant/script.json"
_DST = "assets/produced/elephant/output/the-old-paths_scored.mp4"
_WORKDIR = "assets/produced/elephant/work"

# The Stage-1 FILM-WIDE allocation (beat → curated asset_ids), from the approved curation run.
_ALLOC = {
    1: ["37412828", "37394145"],
    2: ["292151", "292148", "355194", "33660372"],
    3: ["31223126", "126213", "37412830", "37412829"],
    4: ["70877", "126212", "11760750", "34592578"],
    5: ["361057", "126215", "11760745", "33660357"],
    6: ["126214", "126216", "31895173", "33660351"],
    7: ["33660360", "37412784", "36163300", "33660354"],
}


def _load_script():
    d = json.load(open(_SCRIPT))
    beats = tuple(Beat(index=b["index"], label=b["label"], shot_brief=b["shot_brief"],
                       vo=b["vo"], approx_seconds=b["approx_seconds"]) for b in d["beats"])
    return Script(title=d["title"], runtime_target_s=d["runtime_target_s"], word_target=d["word_target"],
                  beats=beats, facts_used=tuple(Fact(**f) for f in d["facts_used"]))


async def _reconstruct(conn):
    """Rebuild {beat.index → [SourcedAsset]} from the DB rows of the curated clips (cached on disk)."""
    sourced, missing = {}, []
    for beat, ids in _ALLOC.items():
        assets = []
        for aid in ids:
            row = await (await conn.execute(
                "SELECT * FROM sourced_assets WHERE asset_id=%s ORDER BY id DESC LIMIT 1", (aid,))).fetchone()
            if not row or not os.path.exists(row["local_path"]):
                missing.append(aid)
                continue
            cand = Candidate(source=row["source"], asset_id=aid, page_url=row["url"],
                             download_url=row["local_path"], licence=row["licence"],
                             width=row["width"] or 1920, height=row["height"] or 1080,
                             contributor=row["contributor"], duration=float(row["duration_s"] or 0) or None,
                             fps=row["fps"], title=row["title"] or "", tags=tuple(row["tags"] or ()))
            gate = GateResult(ok=True, probe=(row.get("gate_report") or {}).get("probe", {}))
            assets.append(SourcedAsset(source=row["source"], asset_id=aid, local_path=row["local_path"],
                                       candidate=cand, gate=gate,
                                       provenance=build_asset_provenance(cand, gate, row["local_path"]),
                                       score=1.0))
        sourced[beat] = assets
    return sourced, missing


async def _make_notifier(settings):
    if settings.bot_token:
        try:
            from telegram import Bot
            from ytagent.notifier import TelegramNotifier
            bot = Bot(settings.bot_token)
            await bot.initialize()
            return TelegramNotifier(bot), bot
        except Exception as e:  # noqa: BLE001
            print(f"  (telegram unavailable — using stub notifier: {e})")
    return StubNotifier(), None


async def _preflight_sfx(music, workdir) -> str:
    """Tiny sound-generation call to report the SFX scope (rule #5). Result discarded."""
    if music is None:
        return "no music provider"
    try:
        os.makedirs(workdir, exist_ok=True)
        r = music.sound_effect("a soft low natural rumble", seconds=1.0,
                               dst=os.path.join(workdir, "_sfx_preflight.mp3"))
        if os.path.exists(r.path):
            os.remove(r.path)
        return "AVAILABLE"
    except MusicScopeError:
        return "BLOCKED (key lacks sound-generation scope)"
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e})"


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    tts = get_tts_provider(settings)
    music = get_music_provider(settings)
    if not (llm and tts and music) or not os.path.exists(_SCRIPT):
        print(f"prereqs — llm={bool(llm)} tts={bool(tts)} music={bool(music)} script={os.path.exists(_SCRIPT)}")
        raise SystemExit(2)

    script = _load_script()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    sourced, missing = await _reconstruct(conn)
    n_clips = sum(len(v) for v in sourced.values())

    print(f"=== ELEPHANT STAGE 2 — '{script.title}' — FULL PRODUCTION (TTS + audio design) ===")
    print(f"curated clips reconstructed: {n_clips}/26 across {len(sourced)} beats"
          + (f"  ⚠ MISSING {missing}" if missing else ""))
    if missing:
        print("ABORT — missing curated clips; re-run Stage 1.")
        await conn.close()
        raise SystemExit(2)

    # ESTIMATE credits BEFORE generating (rule: estimate + report first).
    cues, breathers, breather_s = plan_cues(script, ch)
    cue_cr = sum(c.seconds for c in cues) * _CREDITS_PER_SEC
    bed_cr = _BED_S * _CREDITS_PER_SEC
    spoken_chars = sum(len(v) for k, v in script.to_narration().items() if v.strip())
    print(f"\nAUDIO PLAN: {len(cues)} cues ({', '.join(c.key for c in cues)}) + 1 bed; "
          f"breathers {breather_s:.0f}s at {len(breathers)} transitions")
    print(f"MUSIC ESTIMATE: cues ~{cue_cr:.0f} cr + bed ~{bed_cr:.0f} cr = ~{cue_cr + bed_cr:.0f} credits "
          f"(HARD CEILING 4000)")
    print(f"TTS ESTIMATE: {spoken_chars} chars ≈ {spoken_chars} credits (~£{spoken_chars * 0.00133:.2f})")
    sfx_scope = await _preflight_sfx(music, _WORKDIR)
    print(f"SFX (sound-generation) scope: {sfx_scope} — shipping WITHOUT SFX this run "
          "(placement needs the measured timeline; logged as a follow-up)")

    notifier, bot = await _make_notifier(settings)
    print(f"\nGenerating… (TTS 6 beats, {len(cues)} cues + bed; DRY-RUN publish; approval → Telegram)")
    result = await produce.produce_from_sourced(
        conn, notifier, channel=ch, topic="african elephant", script=script, sourced=sourced,
        tts=tts, music=music, llm_provider=llm, usage_sink=sink, description_exemplar=None,
        publisher=DryRunPublisher(), chat_id=settings.chat_id, dst=_DST, workdir=_WORKDIR,
        budget_credits=4000, sfx_specs=None)

    qc = result["result"].qc
    noise = result["result"].noise
    design = result["design"]
    disclosure = (result["description"].description or "").strip().splitlines()[-1]
    print("\n=== MASTER QC (vs lion benchmark: 1080p/24fps, ~-14 LUFS, 48kHz, no clip, no hiss) ===")
    print(f"  resolution : {qc.get('width')}x{qc.get('height')} @ {qc.get('fps')}fps"
          f"   (lion 1920x1080@24)")
    print(f"  duration   : {qc.get('duration_s')}s ({qc.get('duration_s',0)/60:.1f} min)")
    print(f"  loudness   : {qc.get('loudness_lufs')} LUFS   peak {qc.get('peak_dbfs')} dBFS   "
          f"(target ~-14 / <0)")
    print(f"  noise floor: {qc.get('noise_floor_db')} dB")
    print(f"  audio      : {noise.get('sample_rate')} Hz   >16k={noise.get('hi16k_db')} dB   "
          f">8k={noise.get('hi8k_db')} dB   gate={'PASS' if result['result'].noise_gate.ok else 'FAIL'}")
    print(f"  audio layers: {'; '.join(design.layers) or 'narration only'}")
    print(f"  credits spent (music): {design.credits_spent:.0f} / 4000")
    if design.notes:
        print(f"  audio notes : {'; '.join(design.notes)}")
    print(f"  disclosure : {disclosure}")

    bud = await budget_status(conn)
    print(f"\nSUBMITTED for approval (dry_run). "
          f"month-to-date £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} ({bud['tier']}).")
    print(f"master: {result['result'].output_path}")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

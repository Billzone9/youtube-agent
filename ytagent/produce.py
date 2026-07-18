"""The produce conductor — one NEW video, end to end, autonomously (publish stays the human gate).

Chain: ScriptWriter → source N DISTINCT clips per beat → TTS → bind → density gate → assemble (clips
path, gates) → Description → submit for Telegram approval. Ordering is deliberate: sourcing is free,
TTS costs money, so ALL beats are sourced first and any `NoMatch` fails the whole production BEFORE any
TTS spend. The visual-density standard is enforced twice — N-distinct-clip sourcing fills each beat,
and `assert_visual_density` gates the bound spec before the render. Steps are autonomous within budget;
the submit opens the human gate; the private upload happens later in `handle_decision` on approve.

`remake_from_narration` reuses an existing production's narration mp3s (no TTS re-spend) and re-sources
the visuals to the density standard — the path used to fix a cut whose visuals failed review.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import asdict

from . import repo
from .assembly import assemble_spec, bind_edit_spec
from .assembly import qc as aqc
from .assembly.density import assert_visual_density, min_clips, target_clips
from .assembly.ffmpeg import probe
from .assembly.spec import Target
from .events import record_event
from .metadata.description import generate_description
from .metadata.llm_writer import LLMWriter
from .metadata.research import UnavailableResearch
from .orchestrator import assembly_ping_text, submit_video_for_approval
from .sourcing import NoMatch, source_clips_for_brief

# ElevenLabs multilingual_v2 ≈ 1 credit/char; marginal GBP mirrors the lion-music baseline (£2/1500cr).
_CREDITS_PER_CHAR = 1.0
_GBP_PER_CREDIT = 0.00133
_PRODUCED_ROOT = "assets/produced"


class ProductionError(RuntimeError):
    """A production could not complete (e.g. a shot-brief no-matched) — fails loudly, no partial video."""


async def _drain_llm(conn, sink, pricing, *, channel_id, job_id) -> float:
    from dataclasses import replace as dc_replace

    total = 0.0
    for rec in sink.drain():
        rec = dc_replace(rec, channel_id=rec.channel_id or channel_id, job_id=rec.job_id or job_id)
        total += float((await repo.ledger.write_llm_cost(conn, rec, pricing))["amount_gbp"])
    return total


async def _source_all_beats(conn, providers, script, *, channel_id, job_id, target_fmt, target_w,
                            target_h, cache_dir, llm, length_of) -> dict:
    """Source N DISTINCT clips for every beat (density standard), no clip reused video-wide. Any beat
    that can't reach its minimum fails the WHOLE production (loud, before any TTS spend)."""
    sourced, used, misses = {}, set(), []
    for b in script.beats:
        hint = length_of(b)
        n_min = min_clips(hint)
        n_tgt = max(target_clips(hint), n_min + 1)          # always try for headroom above the minimum
        res = await source_clips_for_brief(
            conn, providers, brief=b.shot_brief, brief_ref=f"{script.title[:24]}:beat{b.index}",
            approx_seconds=int(hint), target_fmt=target_fmt, target_w=target_w, target_h=target_h,
            cache_dir=cache_dir, channel_id=channel_id, job_id=job_id, llm=llm,
            n_target=n_tgt, n_min=n_min, exclude_ids=used)
        if isinstance(res, NoMatch):
            misses.append(f"beat{b.index} ({res.reason})")
        else:
            sourced[b.index] = res
            used |= {(a.source, a.asset_id) for a in res}
    if misses:
        raise ProductionError(
            "insufficient distinct footage for: " + "; ".join(misses) + " — the visual-density "
            "standard needs multiple distinct clips per beat. Pick a better-covered topic or reshape "
            "those beats. No TTS spent.")
    await record_event(conn, "sourced",
                       message=f"{sum(len(v) for v in sourced.values())} clips across {len(sourced)} beats",
                       channel_id=channel_id, job_id=job_id)
    return sourced


def _persist_production(slug: str, script, narration_paths: dict) -> str:
    """Persist the script + its narration mp3s under assets/produced/<slug>/ so a re-make or format
    variant reloads the exact words + audio with zero LLM/TTS re-spend."""
    root = os.path.join(_PRODUCED_ROOT, slug)
    ndir = os.path.join(root, "narration")
    os.makedirs(ndir, exist_ok=True)
    for idx, p in narration_paths.items():
        dst = os.path.join(ndir, f"narr_beat{idx}.mp3")
        if os.path.abspath(p) != os.path.abspath(dst):
            shutil.copy2(p, dst)
    with open(os.path.join(root, "script.json"), "w") as fh:
        json.dump({"title": script.title, "runtime_target_s": script.runtime_target_s,
                   "word_target": script.word_target, "beats": [asdict(b) for b in script.beats],
                   "facts_used": [asdict(f) for f in script.facts_used],
                   "provenance": script.provenance}, fh, indent=2)
    return root


async def _assemble_and_submit(conn, notifier, *, channel, script, sourced, narration, llm_provider,
                               usage_sink, pricing, description_exemplar, publisher, chat_id, dst,
                               workdir, job_id, topic, target_fmt, target_w, target_h) -> dict:
    """Shared tail: bind → density gate → assemble (gates) → describe → submit. Used by both a fresh
    production and a narration-reuse re-make."""
    tgt = Target(fmt=target_fmt, w=target_w, h=target_h, fps=24)
    spec = bind_edit_spec(script, sourced, narration, target=tgt)

    density = assert_visual_density(spec)                   # HARD gate — too-sparse/reused cut fails here
    await record_event(conn, "visual_density_ok",
                       message="; ".join(f"{k}:{v['clips']}clips@{v['shot_s']}s" for k, v in density.items()),
                       channel_id=channel["id"], job_id=job_id, data={"density": density})

    result = await asyncio.to_thread(assemble_spec, spec, dst=dst, provenance_ref="sourced_assets",
                                     workdir=workdir)
    async with conn.transaction():
        await repo.jobs.set_status(conn, job_id, "assembled", result={
            "qc": result.qc, "noise": result.noise, "render_s": result.duration_render_s,
            "density": density})
        await record_event(conn, "produce_assembled",
                           message=f"master {result.qc['duration_s']}s, {len(spec.beats)} beats, noise clean",
                           channel_id=channel["id"], job_id=job_id, data={"qc": result.qc})

    facts = "; ".join(f.claim for f in script.facts_used if f.established)
    writer = LLMWriter(llm_provider, exemplar=description_exemplar)
    desc = generate_description({"topic": topic, "title": script.title, "facts": facts},
                                channel, UnavailableResearch(), writer)
    await _drain_llm(conn, usage_sink, pricing, channel_id=channel["id"], job_id=job_id)

    sub = await submit_video_for_approval(
        conn, notifier, channel=channel, video_meta=result.qc, description=desc,
        chat_id=chat_id, publish_mode=publisher.mode, metadata_source="research_writer")
    await notifier.notify(chat_id=chat_id, text=assembly_ping_text(
        f"{channel['slug']}/produce", ok=True, render_s=result.duration_render_s, qc=result.qc,
        noise_ok=result.noise_gate.ok if result.noise_gate else None)
        + f"\nSubmitted <b>{script.title}</b> for approval ({publisher.mode}).")
    return {"ok": True, "job_id": job_id, "script": script, "sourced": sourced, "density": density,
            "result": result, "description": desc, "submit": sub}


async def produce_video(conn, notifier, *, channel, topic, providers, tts, script_writer,
                        llm_provider, usage_sink, description_exemplar, publisher, chat_id, dst,
                        workdir, runtime_target_s=150, n_beats=4, cache_dir="assets/sourced",
                        target_fmt="16:9", target_w=1920, target_h=1080) -> dict:
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    vp = (channel.get("config") or {}).get("voice_profile") or {}
    voice_id, model = vp.get("voice_id"), vp.get("model", "eleven_multilingual_v2")
    pricing = await repo.ledger.get_llm_pricing(conn)

    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=channel["id"], type="produce",
                                     status="assembling", payload={"topic": topic, "format": target_fmt})
        await record_event(conn, "produce_started", message=f"produce '{topic}'",
                           channel_id=channel["id"], job_id=job["id"])
    jid = job["id"]

    try:
        # 1) SCRIPT (autonomous)
        script = script_writer.write(topic=topic, channel=channel, research=UnavailableResearch(),
                                     runtime_target_s=runtime_target_s, n_beats=n_beats)
        await _drain_llm(conn, usage_sink, pricing, channel_id=channel["id"], job_id=jid)
        await record_event(conn, "script_written",
                           message=f"'{script.title}' — {len(script.beats)} beats, {script.word_count} words",
                           channel_id=channel["id"], job_id=jid)

        # 2) SOURCE ALL beats — N distinct clips each (density), no reuse; NoMatch fails before TTS spend
        sourced = await _source_all_beats(
            conn, providers, script, channel_id=channel["id"], job_id=jid, target_fmt=target_fmt,
            target_w=target_w, target_h=target_h, cache_dir=cache_dir, llm=llm_provider,
            length_of=lambda b: b.approx_seconds or 30)

        # 3) TTS ALL beats (spend) — each narration gated for noise before the render
        if tts is None or not voice_id:
            raise ProductionError("TTS unavailable (no key/scope or no voice_id) — see the plan's "
                                  "Music→TTS scope precondition.")
        narration_texts = script.to_narration()
        narration = {}
        for b in script.beats:
            text = narration_texts[f"beat{b.index}"]
            ndst = os.path.join(workdir, f"narr_beat{b.index}.mp3")
            r = await asyncio.to_thread(tts.synthesize, text, voice_id=voice_id, dst=ndst, model=model)
            g = aqc.check_source_clean(r.path)
            if not g.ok:
                raise ProductionError(f"beat{b.index} narration failed the noise gate: {g.checks}")
            credits = r.characters * _CREDITS_PER_CHAR
            await repo.ledger.write_tts_cost(
                conn, channel_id=channel["id"], job_id=jid, beat_name=f"beat{b.index}",
                characters=r.characters, credits_est=credits,
                amount_gbp_est=round(credits * _GBP_PER_CREDIT, 4), request_id=r.request_id,
                model=model, voice_id=voice_id)
            narration[b.index] = r.path
        await record_event(conn, "narrated", message=f"{len(narration)} beats voiced ({model})",
                           channel_id=channel["id"], job_id=jid)

        # 4) PERSIST script + narration (free re-makes), then 5) bind → density gate → assemble → submit
        _persist_production(spec_slug(script.title), script, narration)
        return await _assemble_and_submit(
            conn, notifier, channel=channel, script=script, sourced=sourced, narration=narration,
            llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
            description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id, dst=dst,
            workdir=workdir, job_id=jid, topic=topic, target_fmt=target_fmt, target_w=target_w,
            target_h=target_h)

    except Exception as e:  # noqa: BLE001 — record + surface any production failure
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=channel["id"], job_id=jid)
        raise


async def remake_from_narration(conn, notifier, *, channel, topic, script, narration_paths, providers,
                                llm_provider, usage_sink, description_exemplar, publisher, chat_id, dst,
                                workdir, cache_dir="assets/sourced", target_fmt="16:9",
                                target_w=1920, target_h=1080) -> dict:
    """Re-make a video from EXISTING narration mp3s (no TTS spend): re-source N distinct clips per beat
    to the density standard, then bind → gate → assemble → submit. `narration_paths`: {beat.index → mp3}
    (the treasured VO, already on disk); `script`: the reconstructed script (labels + shot-briefs steer
    sourcing; the measured mp3 length drives each beat's duration)."""
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pricing = await repo.ledger.get_llm_pricing(conn)
    lengths = {b.index: float(probe(narration_paths[b.index])["duration"]) for b in script.beats}

    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=channel["id"], type="remake",
                                     status="assembling",
                                     payload={"topic": topic, "format": target_fmt, "reuse_narration": True})
        await record_event(conn, "produce_started", message=f"remake '{topic}' (narration reused)",
                           channel_id=channel["id"], job_id=job["id"])
    jid = job["id"]

    try:
        sourced = await _source_all_beats(
            conn, providers, script, channel_id=channel["id"], job_id=jid, target_fmt=target_fmt,
            target_w=target_w, target_h=target_h, cache_dir=cache_dir, llm=llm_provider,
            length_of=lambda b: lengths[b.index])
        _persist_production(spec_slug(script.title), script, narration_paths)
        return await _assemble_and_submit(
            conn, notifier, channel=channel, script=script, sourced=sourced, narration=narration_paths,
            llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
            description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id, dst=dst,
            workdir=workdir, job_id=jid, topic=topic, target_fmt=target_fmt, target_w=target_w,
            target_h=target_h)
    except Exception as e:  # noqa: BLE001
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=channel["id"], job_id=jid)
        raise


def spec_slug(title: str) -> str:
    import re
    return (re.sub(r"[^a-z0-9]+", "-", (title or "video").lower()).strip("-") or "video")[:48]

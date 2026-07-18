"""The produce conductor — one NEW video, end to end, autonomously (publish stays the human gate).

Chain: ScriptWriter → source ALL beats → TTS ALL beats → bind → assemble (clips path, gates) →
Description → submit for Telegram approval. Ordering is deliberate: sourcing is free, TTS costs money,
so ALL beats are sourced first and any `NoMatch` fails the whole production BEFORE any TTS spend.
Steps 1–7 are autonomous within budget; step 8 opens the human gate; the private upload happens later
in `orchestrator.handle_decision` on Banks's approve.
"""
from __future__ import annotations

import asyncio
import os

from . import repo
from .assembly import assemble_spec, bind_edit_spec
from .assembly import qc as aqc
from .assembly.spec import Target
from .events import record_event
from .metadata.description import generate_description
from .metadata.llm_writer import LLMWriter
from .metadata.research import UnavailableResearch
from .orchestrator import assembly_ping_text, submit_video_for_approval
from .sourcing import NoMatch, source_for_brief

# ElevenLabs multilingual_v2 ≈ 1 credit/char; marginal GBP mirrors the lion-music baseline (£2/1500cr).
_CREDITS_PER_CHAR = 1.0
_GBP_PER_CREDIT = 0.00133


class ProductionError(RuntimeError):
    """A production could not complete (e.g. a shot-brief no-matched) — fails loudly, no partial video."""


async def _drain_llm(conn, sink, pricing, *, channel_id, job_id) -> float:
    from dataclasses import replace as dc_replace

    total = 0.0
    for rec in sink.drain():
        rec = dc_replace(rec, channel_id=rec.channel_id or channel_id, job_id=rec.job_id or job_id)
        total += float((await repo.ledger.write_llm_cost(conn, rec, pricing))["amount_gbp"])
    return total


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

        # 2) SOURCE ALL beats (free) — any NoMatch fails BEFORE any TTS spend
        sourced, misses = {}, []
        for b in script.beats:
            res = await source_for_brief(conn, providers, brief=b.shot_brief,
                                         brief_ref=f"{script.title[:24]}:beat{b.index}",
                                         approx_seconds=b.approx_seconds, target_fmt=target_fmt,
                                         target_w=target_w, target_h=target_h, cache_dir=cache_dir,
                                         channel_id=channel["id"], job_id=jid, llm=llm_provider)
            if isinstance(res, NoMatch):
                misses.append(f"beat{b.index} ({res.reason})")
            else:
                sourced[b.index] = res
        await _drain_llm(conn, usage_sink, pricing, channel_id=channel["id"], job_id=jid)
        if misses:
            raise ProductionError("no footage for: " + "; ".join(misses) + " — pick a better-covered "
                                  "topic (coverage-probe first) or reshape those beats. No TTS spent.")
        await record_event(conn, "sourced", message=f"{len(sourced)}/{len(script.beats)} beats sourced",
                           channel_id=channel["id"], job_id=jid)

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

        # 4) BIND → in-memory EditSpec
        tgt = Target(fmt=target_fmt, w=target_w, h=target_h, fps=24)
        spec = bind_edit_spec(script, sourced, narration, target=tgt)

        # 5) ASSEMBLE (clips path, gates) — OUTSIDE any held txn (multi-minute)
        result = await asyncio.to_thread(assemble_spec, spec, dst=dst,
                                         provenance_ref="sourced_assets", workdir=workdir)
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "assembled", result={
                "qc": result.qc, "noise": result.noise, "render_s": result.duration_render_s})
            await record_event(conn, "produce_assembled",
                               message=f"master {result.qc['duration_s']}s, noise clean",
                               channel_id=channel["id"], job_id=jid, data={"qc": result.qc})

        # 6) DESCRIPTION (autonomous)
        facts = "; ".join(f.claim for f in script.facts_used if f.established)
        writer = LLMWriter(llm_provider, exemplar=description_exemplar)
        desc = generate_description({"topic": topic, "title": script.title, "facts": facts},
                                    channel, UnavailableResearch(), writer)
        await _drain_llm(conn, usage_sink, pricing, channel_id=channel["id"], job_id=jid)

        # 7) SUBMIT for approval — the HUMAN GATE (publish happens later on approve)
        sub = await submit_video_for_approval(
            conn, notifier, channel=channel, video_meta=result.qc, description=desc,
            chat_id=chat_id, publish_mode=publisher.mode, metadata_source="research_writer")
        await notifier.notify(chat_id=chat_id, text=assembly_ping_text(
            f"{channel['slug']}/produce", ok=True, render_s=result.duration_render_s, qc=result.qc,
            noise_ok=result.noise_gate.ok if result.noise_gate else None)
            + f"\nSubmitted <b>{script.title}</b> for approval ({publisher.mode}).")
        return {"ok": True, "job_id": jid, "script": script, "sourced": sourced,
                "result": result, "description": desc, "submit": sub}

    except Exception as e:  # noqa: BLE001 — record + surface any production failure
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=channel["id"], job_id=jid)
        raise

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
from .audio_design import generate_audio, plan_cues
from .assembly import assemble_spec, bind_edit_spec
from .assembly import qc as aqc
from .assembly.density import assert_visual_density, min_clips, target_clips
from .assembly.ffmpeg import probe
from .assembly.spec import MusicCue, Sfx, Target
from .budget import budget_status
from .events import record_event
from .metadata.description import generate_description
from .metadata.llm_writer import LLMWriter
from .metadata.research import UnavailableResearch
from .orchestrator import assembly_ping_text, submit_video_for_approval
from .scheduler.cost import estimate_production_cost
from .sourcing import NoMatch, source_clips_for_brief, source_film

# ElevenLabs multilingual_v2 ≈ 1 credit/char; marginal GBP mirrors the lion-music baseline (£2/1500cr).
_CREDITS_PER_CHAR = 1.0
_GBP_PER_CREDIT = 0.00133
_PRODUCED_ROOT = "assets/produced"
# The resumable production stages, in order. A completed stage checkpoints its artifacts + records the
# stage on the job BEFORE the next begins; resume re-enters at the first incomplete stage (6b).
_STAGES = ("scripted", "sourced", "narrated", "designed", "assembled", "submitted")


class ProductionError(RuntimeError):
    """A production could not complete (e.g. a shot-brief no-matched) — fails loudly, no partial video."""


class SpendGatePause(RuntimeError):
    """The 4→5 spend gate would be crossed: either the per-job estimate exceeds the playbook threshold,
    or month-to-date + this estimate would breach the global ceiling. The production PAUSES here (before
    any real money) for Banks; the runner (6c) turns this into a playbook pause + alert."""

    def __init__(self, gate: str, estimate: float, *, limit: float, mtd: float | None = None) -> None:
        self.gate = gate            # "per_job" | "ceiling"
        self.estimate = estimate
        self.limit = limit
        self.mtd = mtd
        super().__init__(f"spend gate '{gate}': estimate £{estimate:.2f}"
                         + (f" + month-to-date £{mtd:.2f}" if mtd is not None else "")
                         + f" vs limit £{limit:.2f}")


class _CrashInjected(RuntimeError):
    """TEST-ONLY: simulates a process death after a stage's WORK completes but BEFORE its checkpoint —
    exercising the resume path (the money-stage idempotency guarantee)."""


async def _drain_llm(conn, sink, pricing, *, channel_id, job_id) -> float:
    from dataclasses import replace as dc_replace

    total = 0.0
    for rec in sink.drain():
        rec = dc_replace(rec, channel_id=rec.channel_id or channel_id, job_id=rec.job_id or job_id)
        total += float((await repo.ledger.write_llm_cost(conn, rec, pricing))["amount_gbp"])
    return total


async def _source_all_beats(conn, providers, script, *, channel_id, job_id, target_fmt, target_w,
                            target_h, cache_dir, llm, length_of, subject) -> dict:
    """FILM-WIDE sourcing + allocation: gather ONE verified pool for the whole film (the SUBJECT forced
    into every beat's queries and into the vision gate), then allocate clips to beats by fit. Any beat
    that can't reach its minimum fails the WHOLE production (loud, before any TTS spend)."""
    beats = [{"index": b.index, "label": b.label, "brief": b.shot_brief,
              "approx_seconds": length_of(b), "n_min": min_clips(length_of(b)),
              "n_target": max(target_clips(length_of(b)), min_clips(length_of(b)) + 1)}
             for b in script.beats]
    alloc, rep = await source_film(
        conn, providers, subject=subject, beats=beats, target_fmt=target_fmt, target_w=target_w,
        target_h=target_h, cache_dir=cache_dir, channel_id=channel_id, job_id=job_id, llm=llm)
    misses = [f"beat{br['beat']} ({br['verified']}/{br['n_min']})"
              for br in rep["beats"] if not br["reached_min"]]
    if misses:
        err = ProductionError(
            "insufficient distinct footage for: " + "; ".join(misses) + f" — the film pool held "
            f"{rep['clear']} clear clips ({rep['rejected']} rejected by the gate) across "
            f"{rep['pool_candidates']} candidates. Pick a better-covered subject or reshape those "
            "beats. No TTS spent.")
        err.clear_count = rep["clear"]        # the ACTUAL yield — the scheduler records it as history
        raise err
    await record_event(conn, "sourced",
                       message=f"{rep['allocated_total']} clips across {len(alloc)} beats "
                               f"(film pool {rep['clear']} clear of {rep['pool_candidates']})",
                       channel_id=channel_id, job_id=job_id)
    return alloc


async def curate_report(conn, providers, script, *, channel_id, job_id=None, llm, target_fmt="16:9",
                        target_w=1920, target_h=1080, cache_dir="assets/sourced", length_of,
                        required_of=None, negative_terms=None) -> list[dict]:
    """STAGE 1 (Amendment 3) — curation + vision gate ONLY, zero music spend. Sources each beat with the
    vision gate and returns a per-beat report (derived per-beat requiredness, verified count vs n_min,
    accepted ids, and every vision verdict) WITHOUT assembling or raising. The no-repeat guard still
    holds across beats so the report reflects a real full source-set. `required_of(beat) -> frozenset`
    gives the per-beat blocking axes (the Amendment). Callers print it and STOP for Banks."""
    report, used = [], set()
    for b in script.beats:
        hint = length_of(b)
        n_min = min_clips(hint)
        n_tgt = max(target_clips(hint), n_min + 1)
        required = required_of(b) if required_of else None
        verdicts: list = []
        res = await source_clips_for_brief(
            conn, providers, brief=b.shot_brief, brief_ref=f"{script.title[:24]}:beat{b.index}",
            approx_seconds=int(hint), target_fmt=target_fmt, target_w=target_w, target_h=target_h,
            cache_dir=cache_dir, channel_id=channel_id, job_id=job_id, llm=llm,
            n_target=n_tgt, n_min=n_min, exclude_ids=used, vision=True, required_axes=required,
            negative_terms=negative_terms, collect_verdicts=verdicts)
        got = [] if isinstance(res, NoMatch) else res
        used |= {(a.source, a.asset_id) for a in got}
        uncertain_used = [v["asset_id"] for v in verdicts
                          if v.get("used") and v.get("category") == "uncertain"]
        from .sourcing.vision import detect_echo
        echo_pairs = detect_echo([(v["asset_id"], v.get("features", ""), v.get("species")) for v in verdicts])
        report.append({"beat": b.index, "label": b.label, "narration_s": round(hint, 1),
                       "required_axes": sorted(required) if required else ["season"],
                       "n_min": n_min, "n_target": n_tgt, "verified": len(got),
                       "clear": len([v for v in verdicts if v.get("category") == "clear"]),
                       "uncertain_used": uncertain_used,
                       "contradictions": sum(1 for v in verdicts if v.get("contradiction")),
                       "echo_pairs": echo_pairs,
                       "reached_min": len(got) >= n_min,
                       "accepted": [{"asset_id": a.asset_id, "url": a.candidate.page_url} for a in got],
                       "verdicts": verdicts,
                       "reason": res.reason if isinstance(res, NoMatch) else "ok"})
    return report


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


async def _tts_all_beats(conn, script, *, tts, voice_id, model, workdir, channel_id, job_id) -> dict:
    """Synthesize the SPOKEN beats (wordless cold-open skipped — no spend), noise-gate each mp3, and
    ledger the per-call TTS estimate. Returns {beat.index → mp3 path}. A hissy narration HARD-fails
    (house rule); a missing key/voice fails loud BEFORE any spend."""
    if tts is None or not voice_id:
        raise ProductionError("TTS unavailable (no key/scope or no voice_id) — see the Music→TTS scope "
                              "precondition.")
    narration_texts = script.to_narration()
    narration = {}
    for b in script.beats:
        text = narration_texts[f"beat{b.index}"]
        if not text.strip():              # WORDLESS beat (cold open) — no TTS call, no spend
            continue
        ndst = os.path.join(workdir, f"narr_beat{b.index}.mp3")
        r = await asyncio.to_thread(tts.synthesize, text, voice_id=voice_id, dst=ndst, model=model)
        g = aqc.check_source_clean(r.path)
        if not g.ok:
            raise ProductionError(f"beat{b.index} narration failed the noise gate: {g.checks}")
        credits = r.characters * _CREDITS_PER_CHAR
        await repo.ledger.write_tts_cost(
            conn, channel_id=channel_id, job_id=job_id, beat_name=f"beat{b.index}",
            characters=r.characters, credits_est=credits,
            amount_gbp_est=round(credits * _GBP_PER_CREDIT, 4), request_id=r.request_id,
            model=model, voice_id=voice_id)
        narration[b.index] = r.path
    await record_event(conn, "narrated", message=f"{len(narration)} beats voiced ({model})",
                       channel_id=channel_id, job_id=job_id)
    return narration


async def _assemble(conn, *, channel, script, sourced, narration, design, dst, workdir, job_id,
                    target_fmt, target_w, target_h):
    """Stage: bind (+ audio design) → density gate → assemble (gates). Returns (result, spec, density).
    All the render gates (density, input+output noise, 48k) apply — a bad cut fails HERE, before submit."""
    tgt = Target(fmt=target_fmt, w=target_w, h=target_h, fps=24)
    dz = design
    spec = bind_edit_spec(script, sourced, narration, target=tgt,
                          cues=(dz.cues if dz else None), breathers=(dz.breathers if dz else None),
                          bed=(dz.bed if dz else None), sfx=(dz.sfx if dz else ()))
    density = assert_visual_density(spec)                   # HARD gate — too-sparse/reused cut fails here
    await record_event(conn, "visual_density_ok",           # skip `_`-prefixed report keys (e.g. _long_holds)
                       message="; ".join(f"{k}:{v['clips']}clips@{v['shot_s']}s"
                                         for k, v in density.items() if not k.startswith("_")),
                       channel_id=channel["id"], job_id=job_id, data={"density": density})
    result = await asyncio.to_thread(assemble_spec, spec, dst=dst, provenance_ref="sourced_assets",
                                     workdir=workdir)
    await record_event(conn, "produce_assembled",
                       message=f"master {result.qc['duration_s']}s, {len(spec.beats)} beats, noise clean",
                       channel_id=channel["id"], job_id=job_id, data={"qc": result.qc})
    return result, spec, density


async def _submit(conn, notifier, *, channel, script, result, design, llm_provider, usage_sink, pricing,
                  description_exemplar, publisher, chat_id, topic, job_id):
    """Stage: describe (manifest-aware) → submit for Telegram approval → completion ping. Returns the
    (description, submit) pair the conductor merges into its result dict."""
    dz = design
    facts = "; ".join(f.claim for f in script.facts_used if f.established)
    writer = LLMWriter(llm_provider, exemplar=description_exemplar)
    desc = generate_description(
        {"topic": topic, "title": script.title, "facts": facts,
         "contents": (dz.manifest if dz and dz.manifest else None)},
        channel, UnavailableResearch(), writer)
    await _drain_llm(conn, usage_sink, pricing, channel_id=channel["id"], job_id=job_id)
    sub = await submit_video_for_approval(
        conn, notifier, channel=channel, video_meta=result.qc, description=desc,
        chat_id=chat_id, publish_mode=publisher.mode, metadata_source="research_writer")
    await notifier.notify(chat_id=chat_id, text=assembly_ping_text(
        f"{channel['slug']}/produce", ok=True, render_s=result.duration_render_s, qc=result.qc,
        noise_ok=result.noise_gate.ok if result.noise_gate else None)
        + f"\nSubmitted <b>{script.title}</b> for approval ({publisher.mode}).")
    return desc, sub


async def _assemble_and_submit(conn, notifier, *, channel, script, sourced, narration, llm_provider,
                               usage_sink, pricing, description_exemplar, publisher, chat_id, dst,
                               workdir, job_id, topic, target_fmt, target_w, target_h,
                               design=None) -> dict:
    """Back-compat wrapper (used by produce_from_sourced / remake_from_narration): assemble → submit in
    one call, recording the `assembled` job status between them, exactly as before the 6b split."""
    result, spec, density = await _assemble(
        conn, channel=channel, script=script, sourced=sourced, narration=narration, design=design,
        dst=dst, workdir=workdir, job_id=job_id, target_fmt=target_fmt, target_w=target_w, target_h=target_h)
    async with conn.transaction():
        await repo.jobs.set_status(conn, job_id, "assembled", result={
            "qc": result.qc, "noise": result.noise, "render_s": result.duration_render_s, "density": density})
    desc, sub = await _submit(
        conn, notifier, channel=channel, script=script, result=result, design=design,
        llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
        description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id, topic=topic,
        job_id=job_id)
    return {"ok": True, "job_id": job_id, "script": script, "sourced": sourced, "density": density,
            "result": result, "description": desc, "submit": sub, "design": design}


# --- resumable production state machine (6b) --------------------------------------------------------
# The production_state dict (persisted in jobs.result['production_state'] + artifacts on disk) lets a
# crashed/restarted run resume at the first INCOMPLETE stage. Deterministic on-disk paths make the money
# stages (TTS, music) idempotent: even a crash AFTER generation but BEFORE the checkpoint reloads the
# artifact instead of re-charging.

def _write_script_json(path: str, script) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"title": script.title, "runtime_target_s": script.runtime_target_s,
                   "word_target": script.word_target, "beats": [asdict(b) for b in script.beats],
                   "facts_used": [asdict(f) for f in script.facts_used],
                   "provenance": script.provenance}, fh, indent=2)


def _load_script_json(path: str):
    from .authoring.script import Beat, Fact, Script
    d = json.load(open(path))
    beats = tuple(Beat(index=b["index"], label=b["label"], shot_brief=b["shot_brief"],
                       vo=b["vo"], approx_seconds=b["approx_seconds"]) for b in d["beats"])
    return Script(title=d["title"], runtime_target_s=d["runtime_target_s"], word_target=d["word_target"],
                  beats=beats, facts_used=tuple(Fact(**f) for f in d["facts_used"]),
                  provenance=d.get("provenance", {}))


async def reconstruct_sourced(conn, allocation: dict) -> dict:
    """Rebuild {beat.index → [SourcedAsset]} from the DB rows of the allocated clips (cached on disk) —
    the resume path for the `sourced` stage (no re-search, no re-vision, no spend)."""
    from .sourcing.base import Candidate, GateResult, SourcedAsset
    from .sourcing.provenance import build_asset_provenance
    out: dict = {}
    for beat_s, items in allocation.items():
        assets = []
        for it in items:
            row = await (await conn.execute(
                "SELECT * FROM sourced_assets WHERE source=%s AND asset_id=%s ORDER BY id DESC LIMIT 1",
                [it["source"], it["asset_id"]])).fetchone()
            if not row or not os.path.exists(row["local_path"]):
                raise ProductionError(f"cached clip missing on resume: {it}")
            cand = Candidate(source=row["source"], asset_id=row["asset_id"], page_url=row["url"],
                             download_url=row["local_path"], licence=row["licence"],
                             width=row["width"] or 1920, height=row["height"] or 1080,
                             contributor=row["contributor"], duration=float(row["duration_s"] or 0) or None,
                             fps=row["fps"], title=row["title"] or "", tags=tuple(row["tags"] or ()))
            gate = GateResult(ok=True, probe=(row.get("gate_report") or {}).get("probe", {}))
            assets.append(SourcedAsset(source=row["source"], asset_id=row["asset_id"],
                                       local_path=row["local_path"], candidate=cand, gate=gate,
                                       provenance=build_asset_provenance(cand, gate, row["local_path"]),
                                       score=1.0))
        out[int(beat_s)] = assets
    return out


_CUE_FILES = {"theme": "cue_theme.mp3", "journey": "cue_journey.mp3", "resolution": "cue_resolution.mp3"}


def _serialize_design(dz) -> dict:
    return {"cues": {str(b): {"file": c.file, "in_db": c.in_db, "fade_in": c.fade_in,
                              "fade_out": c.fade_out} for b, c in dz.cues.items()},
            "breathers": {str(b): s for b, s in dz.breathers.items()}, "bed": dz.bed,
            "sfx": [{"file": s.file, "beat": s.beat, "at_s": s.at_s, "level_db": s.level_db} for s in dz.sfx],
            "manifest": dz.manifest, "credits_spent": dz.credits_spent, "layers": dz.layers}


def _deserialize_design(d: dict):
    from .audio_design import AudioDesign
    dz = AudioDesign()
    dz.cues = {int(b): MusicCue(**c) for b, c in (d.get("cues") or {}).items()}
    dz.breathers = {int(b): s for b, s in (d.get("breathers") or {}).items()}
    dz.bed = d.get("bed")
    dz.sfx = tuple(Sfx(**s) for s in (d.get("sfx") or []))
    dz.manifest = d.get("manifest") or {}
    dz.credits_spent = d.get("credits_spent", 0)
    dz.layers = d.get("layers", [])
    return dz


def _design_files_exist(audio_dir: str) -> bool:
    return any(os.path.exists(os.path.join(audio_dir, f))
               for f in (*_CUE_FILES.values(), "bed.mp3"))


def _design_from_disk(audio_dir: str, script, channel: dict):
    """Reconstruct the AudioDesign from generated cue files already on disk (crash-after-gen resume) —
    reuses the SAME plan_cues assignment the design stage used, so cues map to the right beats."""
    from .audio_design import AudioDesign
    cue_specs, breathers, _ = plan_cues(script, channel)
    dz = AudioDesign(breathers=breathers)
    for spec in cue_specs:
        p = os.path.abspath(os.path.join(audio_dir, _CUE_FILES[spec.key]))
        if os.path.exists(p):
            for bidx in spec.beats:
                dz.cues[bidx] = MusicCue(file=p, in_db=spec.in_db, fade_in=2.0, fade_out=3.0)
    bed = os.path.abspath(os.path.join(audio_dir, "bed.mp3"))
    if os.path.exists(bed):
        dz.bed = bed
    dz.manifest = {"narration": "AI text-to-speech", "footage": "licensed / CC-0 stock"}
    if dz.cues:
        dz.manifest["music"] = "AI-generated instrumental score"
    if dz.bed:
        dz.manifest["ambience"] = "AI-generated"
    return dz


def _initial_state(job: dict) -> dict:
    payload = job.get("payload") or {}
    cfg = payload.get("cfg") or {}
    root = f"{_PRODUCED_ROOT}/job-{job['id']}"
    workdir = cfg.get("workdir") or os.path.join(root, "work")
    dst = cfg.get("dst") or os.path.join(root, "output", "master.mp4")
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    return {"job_id": job["id"], "channel_id": job["channel_id"], "topic": payload.get("topic"),
            "cfg": cfg, "root": root, "workdir": workdir, "dst": dst, "stage": ""}


def _load_state(job: dict) -> dict:
    st = ((job.get("result") or {}).get("production_state"))
    return st if st else _initial_state(job)


async def _checkpoint(conn, state: dict, stage: str, *, extra: dict | None = None) -> None:
    state["stage"] = stage
    if extra:
        state.update(extra)
    status = "assembled" if stage in ("assembled", "submitted") else "assembling"
    async with conn.transaction():
        await repo.jobs.set_status(conn, state["job_id"], status, result={"production_state": state})
        await conn.execute("UPDATE jobs SET stage=%s WHERE id=%s", [stage, state["job_id"]])
        await record_event(conn, "produce_stage", message=f"stage → {stage}",
                           channel_id=state["channel_id"], job_id=state["job_id"], data={"stage": stage})


async def _maybe_checkpoint(conn, state: dict, stage: str, crash_after) -> None:
    if stage in crash_after:
        raise _CrashInjected(stage)     # TEST: money spent this stage, but NO checkpoint — resume must skip
    await _checkpoint(conn, state, stage)


def _before(done: str, stage: str) -> bool:
    d = _STAGES.index(done) if done in _STAGES else -1
    return _STAGES.index(stage) > d


async def _st_script(conn, state, *, script_writer, channel, usage_sink, pricing, providers, llm):
    if state.get("script_path") and os.path.exists(state["script_path"]):
        return _load_script_json(state["script_path"])   # resume: reload, no LLM re-spend
    cfg = state["cfg"]
    # FOOTAGE-LED (6b-bis, STRUCTURAL): obtain the OBSERVED footage distribution BEFORE scripting —
    # the ScriptWriter REQUIRES it, so the auto path physically cannot regress to script-first. Use a
    # pre-supplied distribution (e.g. from the scheduler's probe) if present; else probe now.
    dist = state.get("footage_distribution")
    if not dist:
        from .sourcing.feasibility import probe_feasibility
        rep = await probe_feasibility(conn, providers, state["topic"], llm=llm,
                                      channel_id=state["channel_id"],
                                      runtime_s=cfg.get("runtime_target_s", 150),
                                      n_beats=cfg.get("n_beats", 4))
        dist = {"season": rep.season_dist, "habitat": rep.habitat_dist,
                "time_of_day": rep.time_dist, "shot_type": rep.shot_dist}
        state["footage_distribution"] = dist
        await record_event(conn, "probed",
                           message=f"footage distribution for '{state['topic']}' — "
                                   f"habitat {list((rep.habitat_dist or {}).keys())} "
                                   f"(verdict {rep.verdict}, E={rep.pool_depth})",
                           channel_id=state["channel_id"], job_id=state["job_id"],
                           data={"distribution": dist, "verdict": rep.verdict})
    script = script_writer.write(topic=state["topic"], channel=channel, research=UnavailableResearch(),
                                 footage_distribution=dist, runtime_target_s=cfg.get("runtime_target_s", 150),
                                 n_beats=cfg.get("n_beats", 4))
    await _drain_llm(conn, usage_sink, pricing, channel_id=state["channel_id"], job_id=state["job_id"])
    path = os.path.join(state["root"], "script.json")
    _write_script_json(path, script)
    state["script_path"] = path
    state["title"] = script.title
    await record_event(conn, "script_written",
                       message=f"'{script.title}' — {len(script.beats)} beats, {script.word_count} words",
                       channel_id=state["channel_id"], job_id=state["job_id"])
    return script


async def _st_source(conn, state, *, providers, llm, channel, script):
    if state.get("allocation"):
        return await reconstruct_sourced(conn, state["allocation"])   # resume: rebuild, no re-source
    cfg = state["cfg"]
    sourced = await _source_all_beats(
        conn, providers, script, channel_id=state["channel_id"], job_id=state["job_id"],
        target_fmt=cfg.get("target_fmt", "16:9"), target_w=cfg.get("target_w", 1920),
        target_h=cfg.get("target_h", 1080), cache_dir=cfg.get("cache_dir", "assets/sourced"),
        llm=llm, length_of=lambda b: b.approx_seconds or 30, subject=state["topic"])
    state["allocation"] = {str(b): [{"source": a.source, "asset_id": a.asset_id} for a in assets]
                           for b, assets in sourced.items()}
    return sourced


async def _spend_gate(conn, state, script, *, per_job_threshold_gbp, enforce_ceiling, channel):
    est = estimate_production_cost(script, channel)
    state["estimate_gbp"] = est.total_gbp
    await record_event(conn, "spend_estimate",
                       message=f"est £{est.total_gbp:.2f} (tts £{est.tts_gbp:.2f} + music £{est.music_gbp:.2f})",
                       channel_id=state["channel_id"], job_id=state["job_id"], data=asdict(est))
    if per_job_threshold_gbp is not None and est.total_gbp > float(per_job_threshold_gbp):
        raise SpendGatePause("per_job", est.total_gbp, limit=float(per_job_threshold_gbp))
    if enforce_ceiling:
        bud = await budget_status(conn)
        mtd, ceil = float(bud["month_spend_gbp"]), float(bud["ceiling_gbp"])
        if mtd + est.total_gbp > ceil:
            raise SpendGatePause("ceiling", est.total_gbp, limit=ceil, mtd=mtd)


async def _st_tts(conn, state, *, tts, channel, script):
    cfg = state["cfg"]
    spoken = [b.index for b in script.beats if (b.vo or "").strip()]
    # resume (state) OR disk-robust (deterministic paths) → reload, NEVER re-charge TTS
    saved = {int(k): v for k, v in (state.get("narration_paths") or {}).items()}
    if saved and all(os.path.exists(p) for p in saved.values()):
        return saved
    disk = {b: os.path.join(state["workdir"], f"narr_beat{b}.mp3") for b in spoken}
    if disk and all(os.path.exists(p) for p in disk.values()):
        state["narration_paths"] = {str(k): v for k, v in disk.items()}
        return disk
    narration = await _tts_all_beats(conn, script, tts=tts, voice_id=cfg.get("voice_id"),
                                     model=cfg.get("model", "eleven_multilingual_v2"),
                                     workdir=state["workdir"], channel_id=state["channel_id"],
                                     job_id=state["job_id"])
    state["narration_paths"] = {str(k): v for k, v in narration.items()}
    _persist_production(spec_slug(state.get("title") or state["topic"]), script, narration)
    return narration


async def _st_design(conn, state, *, music, channel, script):
    cfg = state["cfg"]
    audio_dir = os.path.join(state["workdir"], "audio")
    if state.get("design"):
        return _deserialize_design(state["design"])                   # resume from state
    if _design_files_exist(audio_dir):                                # crash-after-gen: reload from disk
        dz = _design_from_disk(audio_dir, script, channel)
        state["design"] = _serialize_design(dz)
        return dz
    dz = await generate_audio(conn, music, script, channel=channel, job_id=state["job_id"],
                              workdir=audio_dir, budget_credits=cfg.get("budget_credits", 4000),
                              sfx_specs=cfg.get("sfx_specs"))
    state["design"] = _serialize_design(dz)
    return dz


async def run_production(conn, notifier, *, job, channel, providers, tts, music, llm_provider,
                         script_writer, usage_sink, description_exemplar, publisher, chat_id,
                         per_job_threshold_gbp=None, enforce_ceiling=False, crash_after=frozenset()) -> dict:
    """Drive a production job through the checkpointed stages, resuming from wherever it left off. Money
    stages reload their artifacts on resume (never re-charge). `crash_after` is TEST-ONLY. A SpendGatePause
    (4→5 gate) or _CrashInjected propagates WITHOUT marking the job failed — the state is preserved for a
    later resume; any other error marks the job failed (assets preserved for a Banks-fixed resume)."""
    state = _load_state(job)
    # RESUME ROBUSTNESS: a restart may have lost the working dirs (or a caller seeded state directly);
    # ensure they exist on EVERY entry, not only at first-run _initial_state.
    os.makedirs(state["workdir"], exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(state["dst"])), exist_ok=True)
    done = state.get("stage") or ""
    pricing = await repo.ledger.get_llm_pricing(conn)
    try:
        script = await _st_script(conn, state, script_writer=script_writer, channel=channel,
                                  usage_sink=usage_sink, pricing=pricing, providers=providers,
                                  llm=llm_provider)
        if _before(done, "scripted"):
            await _maybe_checkpoint(conn, state, "scripted", crash_after)

        sourced = await _st_source(conn, state, providers=providers, llm=llm_provider, channel=channel, script=script)
        if _before(done, "sourced"):
            await _maybe_checkpoint(conn, state, "sourced", crash_after)

        if _before(done, "narrated"):                                 # SPEND GATE (4→5) — only pre-spend
            await _spend_gate(conn, state, script, per_job_threshold_gbp=per_job_threshold_gbp,
                              enforce_ceiling=enforce_ceiling, channel=channel)

        narration = await _st_tts(conn, state, tts=tts, channel=channel, script=script)
        if _before(done, "narrated"):
            await _maybe_checkpoint(conn, state, "narrated", crash_after)

        design = await _st_design(conn, state, music=music, channel=channel, script=script)
        if _before(done, "designed"):
            await _maybe_checkpoint(conn, state, "designed", crash_after)

        cfg = state["cfg"]
        result, spec, density = await _assemble(
            conn, channel=channel, script=script, sourced=sourced, narration=narration, design=design,
            dst=state["dst"], workdir=state["workdir"], job_id=state["job_id"],
            target_fmt=cfg.get("target_fmt", "16:9"), target_w=cfg.get("target_w", 1920),
            target_h=cfg.get("target_h", 1080))
        state["qc"] = result.qc
        if _before(done, "assembled"):
            await _maybe_checkpoint(conn, state, "assembled", crash_after)

        desc, sub = await _submit(
            conn, notifier, channel=channel, script=script, result=result, design=design,
            llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
            description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id,
            topic=state["topic"], job_id=state["job_id"])
        await _checkpoint(conn, state, "submitted")
        return {"ok": True, "job_id": state["job_id"], "script": script, "sourced": sourced,
                "density": density, "result": result, "description": desc, "submit": sub,
                "design": design, "estimate_gbp": state.get("estimate_gbp")}

    except (SpendGatePause, _CrashInjected):
        raise                        # paused/crashed — job state preserved for resume, NOT a failure
    except Exception as e:  # noqa: BLE001 — a real failure: mark failed (assets preserved on disk/state)
        async with conn.transaction():
            await repo.jobs.set_status(conn, state["job_id"], "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=state["channel_id"], job_id=state["job_id"])
        raise


async def produce_video(conn, notifier, *, channel, topic, providers, tts, script_writer,
                        llm_provider, usage_sink, description_exemplar, publisher, chat_id, dst=None,
                        workdir=None, runtime_target_s=150, n_beats=4, cache_dir="assets/sourced",
                        target_fmt="16:9", target_w=1920, target_h=1080, music=None,
                        budget_credits=4000, sfx_specs=None, per_job_threshold_gbp=None,
                        enforce_ceiling=False, crash_after=frozenset(), job=None) -> dict:
    """Produce ONE video end to end via the resumable state machine. Thin wrapper: create (or reuse) the
    job, then `run_production`. Passing `job` resumes an existing production from its checkpoint. dst/
    workdir default to a stable job-keyed root so a resume finds the artifacts; callers may override."""
    vp = (channel.get("config") or {}).get("voice_profile") or {}
    voice_id, model = vp.get("voice_id"), vp.get("model", "eleven_multilingual_v2")
    if job is None:
        cfg = {"runtime_target_s": runtime_target_s, "n_beats": n_beats, "target_fmt": target_fmt,
               "target_w": target_w, "target_h": target_h, "cache_dir": cache_dir,
               "budget_credits": budget_credits, "voice_id": voice_id, "model": model,
               "sfx_specs": sfx_specs}
        if dst:
            cfg["dst"] = os.path.abspath(dst)
        if workdir:
            cfg["workdir"] = os.path.abspath(workdir)
        async with conn.transaction():
            job = await repo.jobs.create(conn, channel_id=channel["id"], type="produce",
                                         status="assembling", payload={"topic": topic, "format": target_fmt,
                                                                       "cfg": cfg})
            await record_event(conn, "produce_started", message=f"produce '{topic}'",
                               channel_id=channel["id"], job_id=job["id"])
    return await run_production(
        conn, notifier, job=job, channel=channel, providers=providers, tts=tts, music=music,
        llm_provider=llm_provider, script_writer=script_writer, usage_sink=usage_sink,
        description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id,
        per_job_threshold_gbp=per_job_threshold_gbp, enforce_ceiling=enforce_ceiling,
        crash_after=crash_after)


async def produce_from_sourced(conn, notifier, *, channel, topic, script, sourced, tts, music,
                               llm_provider, usage_sink, description_exemplar, publisher, chat_id, dst,
                               workdir, target_fmt="16:9", target_w=1920, target_h=1080,
                               budget_credits=4000, sfx_specs=None) -> dict:
    """Produce from ALREADY-sourced clips (skips re-sourcing/vision — the Stage-1 curated set): TTS the
    spoken beats → design audio (cues+bed+sfx) → assemble with the full audio design → submit for
    approval. `sourced`: {beat.index → SourcedAsset | [SourcedAsset]}. Channel-general."""
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    vp = (channel.get("config") or {}).get("voice_profile") or {}
    voice_id, model = vp.get("voice_id"), vp.get("model", "eleven_multilingual_v2")
    pricing = await repo.ledger.get_llm_pricing(conn)
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=channel["id"], type="produce", status="assembling",
                                     payload={"topic": topic, "format": target_fmt, "presourced": True})
        await record_event(conn, "produce_started", message=f"produce '{topic}' (curated clips)",
                           channel_id=channel["id"], job_id=job["id"])
    jid = job["id"]
    try:
        narration = await _tts_all_beats(conn, script, tts=tts, voice_id=voice_id, model=model,
                                         workdir=workdir, channel_id=channel["id"], job_id=jid)
        design = await generate_audio(conn, music, script, channel=channel, job_id=jid,
                                      workdir=os.path.join(workdir, "audio"),
                                      budget_credits=budget_credits, sfx_specs=sfx_specs)
        _persist_production(spec_slug(script.title), script, narration)
        return await _assemble_and_submit(
            conn, notifier, channel=channel, script=script, sourced=sourced, narration=narration,
            llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
            description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id, dst=dst,
            workdir=workdir, job_id=jid, topic=topic, target_fmt=target_fmt, target_w=target_w,
            target_h=target_h, design=design)
    except Exception as e:  # noqa: BLE001
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=channel["id"], job_id=jid)
        raise


async def remake_from_narration(conn, notifier, *, channel, topic, script, narration_paths, providers,
                                llm_provider, usage_sink, description_exemplar, publisher, chat_id, dst,
                                workdir, cache_dir="assets/sourced", target_fmt="16:9",
                                target_w=1920, target_h=1080, music=None, budget_credits=4000,
                                sfx_specs=None) -> dict:
    """Re-make a video from EXISTING narration mp3s (no TTS spend): re-source N distinct clips per beat
    to the density standard, then bind → gate → assemble → submit. `narration_paths`: {beat.index → mp3}
    (the treasured VO, already on disk); `script`: the reconstructed script (labels + shot-briefs steer
    sourcing; the measured mp3 length drives each beat's duration)."""
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pricing = await repo.ledger.get_llm_pricing(conn)
    # wordless beats (no narration path) use their declared approx_seconds, not a measured length
    lengths = {b.index: (float(probe(narration_paths[b.index])["duration"])
                         if narration_paths.get(b.index) else float(b.approx_seconds))
               for b in script.beats}

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
            length_of=lambda b: lengths[b.index], subject=topic)
        design = await generate_audio(conn, music, script, channel=channel, job_id=jid,
                                      workdir=os.path.join(workdir, "audio"),
                                      budget_credits=budget_credits, sfx_specs=sfx_specs)
        _persist_production(spec_slug(script.title), script, narration_paths)
        return await _assemble_and_submit(
            conn, notifier, channel=channel, script=script, sourced=sourced, narration=narration_paths,
            llm_provider=llm_provider, usage_sink=usage_sink, pricing=pricing,
            description_exemplar=description_exemplar, publisher=publisher, chat_id=chat_id, dst=dst,
            workdir=workdir, job_id=jid, topic=topic, target_fmt=target_fmt, target_w=target_w,
            target_h=target_h, design=design)
    except Exception as e:  # noqa: BLE001
        async with conn.transaction():
            await repo.jobs.set_status(conn, jid, "failed", error=str(e))
            await record_event(conn, "produce_failed", message=str(e),
                               channel_id=channel["id"], job_id=jid)
        raise


def spec_slug(title: str) -> str:
    import re
    return (re.sub(r"[^a-z0-9]+", "-", (title or "video").lower()).strip("-") or "video")[:48]

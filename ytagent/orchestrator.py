"""The conductor. Composes repo + events + a Publisher + a Notifier into the
submit -> approve/reject -> publish flow. Depends on PROTOCOLS (Publisher, Notifier), never on
googleapiclient or python-telegram-bot. Every state change goes through events.record_event.

The approve path is THREE phases so a long real upload never holds a DB transaction:
  1. txn: decide + mark uploading + record upload_started
  2. no txn: await publisher.publish(...)   <- the (possibly multi-minute) upload
  3. txn: persist the result (or mark failed)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from psycopg.types.json import Jsonb

from . import repo
from .budget import budget_status
from .events import record_event
from .publish import PRIVACY_LOCKED, ChannelMismatchError   # runtime — plain values, no googleapiclient

if TYPE_CHECKING:  # avoid importing transports/impls at runtime
    from .metadata.description import Description
    from .notifier import Notifier
    from .publish import Publisher, PublishResult


def _fmt_num(v: Any, suffix: str = "", nd: int = 1) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return f"{v}{suffix}"


def _format_approval_text(video: dict, channel: dict, budget: dict, publish_mode: str) -> str:
    dur = video.get("duration_s")
    mins = f"{int(dur) // 60}:{int(dur) % 60:02d}" if dur else "—"
    size_mb = f"{video['size_bytes'] / 1_000_000:.1f} MB" if video.get("size_bytes") else "—"
    handle = (channel.get("config") or {}).get("youtube_handle") or channel["name"]
    if publish_mode == "live":
        action = (
            f"⬆️ On approval: uploads <b>PRIVATELY</b> to {handle} (real upload — visible only to "
            f"you; you verify it and flip it public yourself)."
        )
    else:
        action = "⚠️ Publishing is a DRY RUN — no real upload."
    return (
        f"🎬 <b>Approval needed — publish</b>\n"
        f"Channel: <b>{channel['name']}</b>\n"
        f"Title: <b>{video['title']}</b>\n\n"
        f"Duration: {mins} ({_fmt_num(dur, 's')})  •  "
        f"{video.get('width','?')}×{video.get('height','?')} @ {_fmt_num(video.get('fps'),'fps',0)}\n"
        f"Loudness: {_fmt_num(video.get('loudness_lufs'),' LUFS')}  •  "
        f"Peak: {_fmt_num(video.get('peak_dbfs'),' dBFS')}\n"
        f"File: {size_mb}\n"
        f"Provenance: <code>{video.get('provenance_ref') or '—'}</code>\n\n"
        f"💷 Month-to-date spend: <b>£{budget['month_spend_gbp']:.2f}</b> "
        f"/ £{budget['ceiling_gbp']:.0f} ({budget['tier']})\n\n"
        f"{action}"
    )


def _resolved_text(video: dict, result: "PublishResult", decided_by: str, *, is_publish: bool = False) -> str:
    if result.mode == "live":
        vid = result.youtube_video_id
        if is_publish:
            return (
                f"✅ <b>Published — PUBLIC</b> by {decided_by}\n"
                f"<b>{video['title']}</b> is live (clean description).\n"
                f"YouTube id: <code>{vid}</code>\n"
                f'Watch: <a href="https://youtu.be/{vid}">youtu.be/{vid}</a>  —  please confirm visually.'
            )
        return (
            f"✅ <b>Published (private)</b> by {decided_by}\n"
            f"<b>{video['title']}</b>\n"
            f"YouTube id: <code>{vid}</code>\n"
            f'Verify (private): <a href="https://studio.youtube.com/video/{vid}/edit">YouTube Studio</a>'
        )
    st = result.body["status"]
    action = "would go PUBLIC (videos.update)" if is_publish else "no real upload"
    text = (
        f"✅ <b>Approved</b> by {decided_by}\n"
        f"<b>{video['title']}</b> — DRY RUN ({action}).\n"
        f"privacyStatus: <code>{st['privacyStatus']}</code>  •  "
        f"synthetic-media disclosed: <code>true</code>"
    )
    val = result.validation or {}
    if "size_matches" in val:   # insert dry-run carries a media check; the update path does not
        text += (f"\nfile check: {'✅ size matches' if val['size_matches'] else '⚠️ size mismatch'} "
                 f"({val.get('size_bytes_actual')} bytes)")
    return text


def _format_publish_public_text(video: dict, channel: dict, clean: dict, publish_mode: str) -> str:
    """Card for PUBLISHING an already-uploaded video to PUBLIC with a clean description. The channel id
    is shown + verified so a documentary can never be flipped public on the wrong channel silently."""
    handle = (channel.get("config") or {}).get("youtube_handle") or channel["name"]
    chan_id = (channel.get("config") or {}).get("youtube_channel_id") or "—"
    yt = video.get("youtube_video_id")
    desc = (clean.get("description") or "")
    preview = (desc[:280] + "…") if len(desc) > 280 else desc
    if publish_mode == "live":
        action = (f"🌐 On approval: sets the CLEAN description and flips <b>{yt}</b> to <b>PUBLIC</b> on "
                  f"{handle}\n(channel <code>{chan_id}</code> — verified before the write). You confirm "
                  "visually after.")
    else:
        action = "⚠️ DRY RUN — builds + guard-scans the public body, no real change."
    return (
        f"🌐 <b>Approval needed — PUBLISH (go public)</b>\n"
        f"Channel: <b>{channel['name']}</b>  •  <code>{chan_id}</code>\n"
        f"Video: <b>{clean.get('title')}</b>\n"
        f"Already uploaded (private): <code>{yt}</code>\n\n"
        f"New public description (clean, guard-passed):\n<code>{preview}</code>\n\n"
        f"{action}"
    )


async def submit_publish_for_approval(
    conn, notifier: "Notifier", *, channel: dict, video: dict, clean: dict, chat_id: str,
    publish_mode: str = "dry_run",
) -> dict:
    """Gate PUBLISHING an already-uploaded video to PUBLIC with a clean, guard-passed description.
    `video` is the existing (private) video row; `clean` is the authored version to apply
    (id/version/title/description/tags). Creates a `publish_public` job + approval and sends the card.
    handle_decision routes on job.type: on approve it calls publisher.update_public (videos.update)."""
    from .metadata.guard import assert_no_internal_artifacts
    assert_no_internal_artifacts(clean["title"], clean["description"], *(clean.get("tags") or []))
    payload = {
        "action": "publish_public", "publish_mode": publish_mode,
        "video_id": video["id"], "youtube_video_id": video.get("youtube_video_id"),
        "metadata_id": clean["id"], "metadata_version": clean.get("version"),
        "clean": {"title": clean["title"], "description": clean["description"],
                  "tags": list(clean.get("tags") or [])},
    }
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=channel["id"], type="publish_public",
                                     status="awaiting_approval", stage="publish", payload=payload)
        approval = await repo.approvals.create(
            conn, channel_id=channel["id"], job_id=job["id"], kind="publish", telegram_chat_id=chat_id)
        await record_event(
            conn, "publish_public_submitted",
            message=f"submitted '{clean['title']}' to go PUBLIC (video {video.get('youtube_video_id')})",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"video_id": video["id"], "metadata_version": clean.get("version")})
    text = _format_publish_public_text(video, channel, clean, publish_mode)
    message_id = await notifier.send_approval_request(chat_id=chat_id, text=text, approval_id=approval["id"])
    async with conn.transaction():
        approval = await repo.approvals.set_message_id(conn, approval["id"], message_id)
        await record_event(conn, "approval_requested", message="sent Telegram approval request",
                           channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
                           data={"telegram_message_id": message_id})
    return {"job": job, "approval": approval, "message_id": message_id}


async def submit_video_for_approval(
    conn, notifier: "Notifier", *, channel: dict, video_meta: dict, description: "Description",
    chat_id: str, publish_mode: str = "dry_run", metadata_source: str = "manual",
) -> dict:
    # Public text comes from the authored Description (title/description/tags); video_meta is the
    # INTERNAL technical payload only. The two are joined here — the internal one never reaches a
    # public field, and the authored text is recorded as video_metadata v1 for the audit/history.
    pub = description.to_public_dict()
    async with conn.transaction():
        job = await repo.jobs.create(
            conn, channel_id=channel["id"], type="publish", status="awaiting_approval",
            stage="publish", payload={"title": pub["title"], "publish_mode": publish_mode},
        )
        video = await repo.videos.create(
            conn, channel_id=channel["id"], job_id=job["id"], status="awaiting_approval",
            title=pub["title"], description=pub["description"], tags=Jsonb(pub["tags"]), **video_meta,
        )
        meta = await repo.metadata.create_version(
            conn, video_id=video["id"], channel_id=channel["id"], title=pub["title"],
            description=pub["description"], tags=pub["tags"], source=metadata_source,
        )
        approval = await repo.approvals.create(
            conn, channel_id=channel["id"], job_id=job["id"], kind="publish", telegram_chat_id=chat_id
        )
        await record_event(
            conn, "video_submitted", message=f"submitted '{video['title']}' for publish approval",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"video_id": video["id"], "publish_mode": publish_mode},
        )
        await record_event(
            conn, "metadata_version", message=f"stored authored metadata v{meta['version']}",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"video_id": video["id"], "metadata_id": meta["id"], "version": meta["version"],
                  "source": metadata_source},
        )

    budget = await budget_status(conn)
    text = _format_approval_text(video, channel, budget, publish_mode)
    message_id = await notifier.send_approval_request(
        chat_id=chat_id, text=text, approval_id=approval["id"]
    )

    async with conn.transaction():
        approval = await repo.approvals.set_message_id(conn, approval["id"], message_id)
        await record_event(
            conn, "approval_requested", message="sent Telegram approval request",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"telegram_message_id": message_id},
        )
    return {"job": job, "video": video, "approval": approval, "message_id": message_id, "budget": budget}


def _format_spend_text(channel: dict, gate: str, estimate: float, limit: float, unit: str,
                       mtd, breakdown: dict) -> str:
    """The spend-approval card: WHY it paused + the per-provider breakdown, so Banks decides with the
    numbers in front of him (B3 item 3). Approve resumes without re-charging done stages; reject holds."""
    if gate == "credits":
        why = (f"ElevenLabs key can't fund this: needs <b>{estimate:.0f}</b> credits, "
               f"has <b>{limit:.0f}</b>. Raise the cap (dashboard + ELEVENLABS_KEY_CREDIT_CAP).")
    elif gate == "ceiling":
        why = (f"month-to-date £{(mtd or 0):.2f} + est £{estimate:.2f} would breach the "
               f"£{limit:.0f} monthly ceiling.")
    else:
        why = f"estimate £{estimate:.2f} exceeds the per-job £{limit:.2f} threshold."
    lines = [f"⏸️ <b>{channel['name']} — spend approval</b>", why, ""]
    tts_c = breakdown.get("tts_chars", 0)
    mus_c = breakdown.get("music_credits", 0)
    sfx_c = breakdown.get("sfx_credits", 0)
    lines.append(f"<b>Estimate</b> £{breakdown.get('total_gbp', 0):.2f}  "
                 f"({tts_c + mus_c + sfx_c:.0f} EL credits)")
    lines.append(f"• TTS: £{breakdown.get('tts_gbp', 0):.2f} ({tts_c:.0f} cr)")
    lines.append(f"• Music+SFX: £{breakdown.get('music_gbp', 0) + breakdown.get('sfx_gbp', 0):.2f} "
                 f"({mus_c + sfx_c:.0f} cr)")
    lines.append(f"• LLM (description): £{breakdown.get('llm_gbp', 0):.2f}")
    lines.append("\nApprove to resume (no re-charge of voiced beats / generated music) · Reject to hold.")
    return "\n".join(lines)


async def submit_spend_for_approval(
    conn, notifier: "Notifier", *, channel: dict, job: dict, gate: str, estimate: float, limit: float,
    unit: str = "£", mtd=None, breakdown: dict | None = None, chat_id: str,
) -> dict:
    """Open the HUMAN spend gate on Telegram for a PAUSED production (B3 item 3). Creates a 'spend'
    approval on the existing job and sends the inline Approve/Reject card with the breakdown; the
    callback routes through handle_decision (kind='spend') → approve_spend on approve."""
    async with conn.transaction():
        approval = await repo.approvals.create(
            conn, channel_id=channel["id"], job_id=job["id"], kind="spend", telegram_chat_id=chat_id)
        await record_event(
            conn, "spend_approval_requested", message=f"spend gate '{gate}' — awaiting Banks",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"gate": gate, "estimate": estimate, "limit": limit, "unit": unit})
    text = _format_spend_text(channel, gate, estimate, limit, unit, mtd, breakdown or {})
    message_id = await notifier.send_approval_request(chat_id=chat_id, text=text, approval_id=approval["id"])
    async with conn.transaction():
        approval = await repo.approvals.set_message_id(conn, approval["id"], message_id)
    return {"approval": approval, "message_id": message_id}


async def handle_decision(
    conn, notifier: "Notifier", publisher: "Publisher", *, approval_id: int, decision: str,
    decided_by: str,
) -> dict:
    state = "approved" if decision == "approve" else "rejected"

    # --- Phase 1: decide, fetch context, mark state (txn) ---
    async with conn.transaction():
        approval = await repo.approvals.decide(conn, approval_id, state, decided_by=decided_by)
        if approval is None:
            return {"handled": False, "reason": "already_decided_or_missing", "approval_id": approval_id}
        job = await repo.jobs.get(conn, approval["job_id"])
        channel = await repo.channels.get_by_id(conn, approval["channel_id"])
        await record_event(
            conn, f"approval_{state}", message=f"spend approval {state} by {decided_by}",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
        ) if approval["kind"] == "spend" else None
        # SPEND gate (B3 item 3) — NOT a publish; approve un-gates the paused production, reject keeps it
        # paused. Handled here and returned before any publish/video logic (a paused job has no video).
        if approval["kind"] == "spend":
            if decision == "approve":
                from .scheduler.runner import approve_spend
                await approve_spend(conn, job["id"])   # flag spend_approved + playbook→producing (resumes next tick)
            spend_ctx = {"chat_id": approval.get("telegram_chat_id"),
                         "msg_id": approval.get("telegram_message_id"), "job_id": job["id"]}
        else:
            spend_ctx = None
        payload = job.get("payload") or {}
        is_publish = job.get("type") == "publish_public"
        if spend_ctx is None:
            # publish_public acts on an EXISTING uploaded video (by payload id); upload uses the job's video.
            video = (await repo.videos.get(conn, payload["video_id"]) if is_publish
                     else await repo.videos.get_by_job(conn, approval["job_id"]))
            await record_event(
                conn, f"approval_{state}", message=f"approval {state} by {decided_by}",
                channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            )
            if decision == "reject":
                await repo.jobs.set_status(conn, job["id"], "rejected")
                await repo.videos.set_status(conn, video["id"], "rejected" if not is_publish else video["status"])
            else:
                await repo.jobs.set_status(conn, job["id"], "running")
                await repo.videos.set_status(conn, video["id"], "publishing" if is_publish else "uploading")
                await record_event(
                    conn, "upload_started",
                    message=f"{publisher.mode} {'publish-to-public' if is_publish else 'upload'} started",
                    channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
                    data={"mode": publisher.mode, "action": job.get("type")},
                )

    chat_id = approval.get("telegram_chat_id")
    msg_id = approval.get("telegram_message_id")

    # SPEND decision resolves here — update the card and return (no publish, no video)
    if spend_ctx is not None:
        if msg_id:
            resolved = (f"✅ <b>Spend approved</b> by {decided_by} — job {job['id']} resumes on the next "
                        f"tick (no re-charge of voiced beats / generated music)."
                        if decision == "approve" else
                        f"❌ <b>Spend rejected</b> by {decided_by} — job {job['id']} stays paused; nothing spent.")
            await notifier.update_resolved(chat_id=chat_id, message_id=msg_id, text=resolved)
        return {"handled": True, "decision": decision, "job_id": job["id"], "kind": "spend"}

    if decision == "reject":
        if msg_id:
            await notifier.update_resolved(
                chat_id=chat_id, message_id=msg_id,
                text=f"❌ <b>Rejected</b> by {decided_by}\n<b>{video['title']}</b> — not published.",
            )
        return {"handled": True, "decision": "reject", "job_id": job["id"]}

    verb = "publishing (public)" if is_publish else "uploading"
    if publisher.mode == "live" and msg_id:
        await notifier.update_resolved(
            chat_id=chat_id, message_id=msg_id,
            text=f"⏳ <b>Approved</b> — {verb} <b>{video['title']}</b>…",
        )

    # For publish_public, overlay the clean authored snippet onto the video IN MEMORY (the DB record is
    # only updated once the write actually succeeds — never before).
    if is_publish:
        clean = payload.get("clean") or {}
        video = {**video, "title": clean.get("title") or video["title"],
                 "description": clean.get("description") or video.get("description"),
                 "tags": clean.get("tags") or video.get("tags")}

    # --- Phase 2: the write — NO DB transaction held ---
    try:
        result = await (publisher.update_public(video, channel) if is_publish
                        else publisher.publish(video, channel))
    except ChannelMismatchError as e:   # Amendment A BACKSTOP — the write may have landed on the WRONG
        return await _record_misplaced(  # channel (insert is irreversible); record + alert, don't publish
            conn, notifier, channel=channel, job=job, video=video, approval=approval,
            chat_id=chat_id, msg_id=msg_id, err=e)
    except Exception as e:  # noqa: BLE001 — record any failure and surface it
        async with conn.transaction():
            await repo.jobs.set_status(conn, job["id"], "failed", error=str(e))
            await repo.videos.set_status(conn, video["id"], "failed")
            await record_event(
                conn, "upload_failed", message=str(e),
                channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            )
        if msg_id:
            await notifier.update_resolved(
                chat_id=chat_id, message_id=msg_id,
                text=f"⚠️ <b>{'Publish' if is_publish else 'Upload'} failed</b>\n"
                     f"<b>{video['title']}</b>\n<code>{e}</code>",
            )
        return {"handled": True, "decision": "approve", "job_id": job["id"], "error": str(e)}

    # --- Phase 3: persist the result (txn) ---
    async with conn.transaction():
        # A DRY RUN changes NOTHING on YouTube — never record 'public' privacy for it (it would be a lie
        # in the DB). Only a real (live) call may persist the result's privacy_status.
        persisted_privacy = result.privacy_status if result.mode == "live" else PRIVACY_LOCKED
        await repo.videos.set_published(
            conn, video["id"], youtube_video_id=result.youtube_video_id,
            privacy_status=persisted_privacy, published_at=result.published_at,
            status=result.video_status,
        )
        if result.mode == "live":
            if is_publish:
                # the videos.update SET the clean snippet + public — the applied version is now live
                await repo.metadata.mark_applied(
                    conn, payload["metadata_id"], applied_at=result.published_at,
                    applied_via="update_publish")
            else:
                # a real insert SETS the description at upload, so the latest authored version is now live
                meta = await repo.metadata.get_latest_authored(conn, video["id"])
                if meta is not None and meta.get("applied_at") is None:
                    await repo.metadata.mark_applied(
                        conn, meta["id"], applied_at=result.published_at, applied_via="upload_insert")
        await repo.jobs.set_status(conn, job["id"], result.job_status, result=result.to_dict())
        if is_publish:
            ev_type = "published_public" if result.mode == "live" else "dry_run_published"
            ev_msg = ("published PUBLICLY to YouTube (clean description)" if result.mode == "live"
                      else "DRY RUN — would publish to public (no real change)")
        else:
            ev_type = "published" if result.mode == "live" else "dry_run_published"
            ev_msg = ("published PRIVATELY to YouTube" if result.mode == "live"
                      else "DRY RUN — would publish (no real upload)")
        await record_event(
            conn, ev_type, message=ev_msg, channel_id=channel["id"], job_id=job["id"],
            approval_id=approval["id"], data=result.to_dict(),
        )

    if msg_id:
        await notifier.update_resolved(
            chat_id=chat_id, message_id=msg_id,
            text=_resolved_text(video, result, decided_by, is_publish=is_publish))
    return {
        "handled": True, "decision": "approve", "job_id": job["id"],
        "video_id": video["id"], "result": result.to_dict(),
    }


async def _record_misplaced(conn, notifier, *, channel, job, video, approval, chat_id, msg_id,
                            err: ChannelMismatchError) -> dict:
    """Amendment A: an upload/update landed on the WRONG channel. Insert is irreversible, so record the
    stray video MISPLACED (never 'published'), store its id, and alert Banks to delete it by hand."""
    async with conn.transaction():
        await repo.jobs.set_status(conn, job["id"], "failed", error=str(err))
        await repo.videos.set_published(
            conn, video["id"], youtube_video_id=err.youtube_video_id, privacy_status="private",
            published_at=None, status="misplaced")
        await record_event(
            conn, "upload_misplaced",
            message=f"CHANNEL MISMATCH — stray video {err.youtube_video_id} on {err.actual!r}, "
                    f"expected {err.expected!r}; recorded MISPLACED (not published)",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"youtube_video_id": err.youtube_video_id, "actual_channel": err.actual,
                  "expected_channel": err.expected})
    alert = (f"🚨 <b>MISPLACED — wrong channel</b>\n<b>{video['title']}</b>\n"
             f"Landed on <code>{err.actual}</code>, expected <code>{err.expected}</code>.\n"
             f"Stray video id: <code>{err.youtube_video_id}</code>\n"
             f"NOT published. DELETE IT MANUALLY: "
             f"https://studio.youtube.com/video/{err.youtube_video_id}/edit")
    if msg_id:
        await notifier.update_resolved(chat_id=chat_id, message_id=msg_id, text=alert)
    else:
        await notifier.notify(chat_id=chat_id, text=alert)
    return {"handled": True, "decision": "approve", "job_id": job["id"], "misplaced": True,
            "youtube_video_id": err.youtube_video_id}


# --- Slice 3: assembly job + one-line completion ping (reuses the Notifier seam) --------------

_QC_COLS = ("file_path", "format", "duration_s", "width", "height", "fps", "loudness_lufs",
            "peak_dbfs", "noise_floor_db", "size_bytes", "checksum", "provenance_ref")


def assembly_ping_text(label: str, *, ok: bool, render_s: float, qc: dict, comparison=None,
                       noise_ok: bool | None = None) -> str:
    """One line for Telegram: result · render time · runtime · QC pass/fail · audio-clean."""
    parts = [f"🎬 Assemble <b>{label}</b>: {'✅ done' if ok else '⚠️ FAILED'}"]
    if render_s:
        parts.append(f"render {render_s:.0f}s")
    dur = (qc or {}).get("duration_s")
    if dur:
        parts.append(f"{int(dur // 60)}:{int(dur % 60):02d}")
    if comparison is not None:
        parts.append(f"QC {'PASS ✅' if comparison.ok else 'FAIL ❌'}")
    if noise_ok is not None:
        parts.append("audio 🔇 clean" if noise_ok else "audio ⚠️ NOISE")
    return " · ".join(parts)


async def record_assembly(
    conn, notifier: "Notifier", *, channel: dict, spec_path: str, dst: str, chat_id: str,
    fmt: str = "16:9", reference: dict | None = None, provenance_ref: str | None = None,
    title: str | None = None,
) -> dict:
    """Run an assemble job: record it, render OUTSIDE any held txn (ffmpeg is multi-minute),
    persist the artifact as a draft `videos` row from the measured QC, and ping Banks one line."""
    import asyncio
    import os

    from .assembly import assembler

    label = f"{channel['slug']}/{fmt}"
    title = title or os.path.splitext(os.path.basename(spec_path))[0]

    # Phase 1: record the job (txn)
    async with conn.transaction():
        job = await repo.jobs.create(
            conn, channel_id=channel["id"], type="assemble", status="assembling", stage="assemble",
            payload={"spec": spec_path, "format": fmt, "dst": dst},
        )
        await record_event(conn, "assembly_started", message=f"assembling {label}",
                           channel_id=channel["id"], job_id=job["id"],
                           data={"spec": spec_path, "dst": dst, "format": fmt})

    # Phase 2: the render — NO DB transaction held
    try:
        result = await asyncio.to_thread(
            assembler.assemble, spec_path, fmt=fmt, dst=dst, reference=reference,
            provenance_ref=provenance_ref,
        )
    except Exception as e:  # noqa: BLE001 — record + surface any render failure
        async with conn.transaction():
            await repo.jobs.set_status(conn, job["id"], "failed", error=str(e))
            await record_event(conn, "assembly_failed", message=str(e),
                               channel_id=channel["id"], job_id=job["id"])
        await notifier.notify(chat_id=chat_id,
                              text=f"🎬 Assemble <b>{label}</b>: ⚠️ FAILED\n<code>{e}</code>")
        return {"ok": False, "job_id": job["id"], "error": str(e)}

    # Phase 3: persist the artifact + close the job (txn)
    async with conn.transaction():
        video = await repo.videos.create(
            conn, channel_id=channel["id"], job_id=job["id"], status="draft", title=title,
            **{k: result.qc.get(k) for k in _QC_COLS},
        )
        noise_ok = result.noise_gate.ok if result.noise_gate else None
        await repo.jobs.set_status(conn, job["id"], "assembled", result={
            "qc": result.qc, "video_id": video["id"], "render_s": result.duration_render_s,
            "comparison_ok": (result.comparison.ok if result.comparison else None),
            "noise": result.noise, "noise_ok": noise_ok, "provenance": result.provenance,
        })
        await record_event(
            conn, "assembly_completed",
            message=f"assembled {label} ({result.qc.get('duration_s')}s, "
                    f"QC {'pass' if (result.comparison and result.comparison.ok) else 'n/a'}, "
                    f"noise {'clean' if noise_ok else 'n/a'})",
            channel_id=channel["id"], job_id=job["id"],
            data={"video_id": video["id"], "qc": result.qc, "noise": result.noise},
        )

    await notifier.notify(chat_id=chat_id, text=assembly_ping_text(
        label, ok=result.ok, render_s=result.duration_render_s, qc=result.qc,
        comparison=result.comparison, noise_ok=noise_ok))
    return {"ok": True, "job_id": job["id"], "video_id": video["id"], "result": result}

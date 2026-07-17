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


def _resolved_text(video: dict, result: "PublishResult", decided_by: str) -> str:
    if result.mode == "live":
        vid = result.youtube_video_id
        return (
            f"✅ <b>Published (private)</b> by {decided_by}\n"
            f"<b>{video['title']}</b>\n"
            f"YouTube id: <code>{vid}</code>\n"
            f'Verify (private): <a href="https://studio.youtube.com/video/{vid}/edit">YouTube Studio</a>'
        )
    val = result.validation
    st = result.body["status"]
    return (
        f"✅ <b>Approved</b> by {decided_by}\n"
        f"<b>{video['title']}</b> — DRY RUN published (no real upload).\n"
        f"privacyStatus: <code>{st['privacyStatus']}</code>  •  "
        f"synthetic-media disclosed: <code>true</code>\n"
        f"file check: {'✅ size matches' if val['size_matches'] else '⚠️ size mismatch'} "
        f"({val['size_bytes_actual']} bytes)"
    )


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
        video = await repo.videos.get_by_job(conn, approval["job_id"])
        channel = await repo.channels.get_by_id(conn, approval["channel_id"])
        await record_event(
            conn, f"approval_{state}", message=f"approval {state} by {decided_by}",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
        )
        if decision == "reject":
            await repo.jobs.set_status(conn, job["id"], "rejected")
            await repo.videos.set_status(conn, video["id"], "rejected")
        else:
            await repo.jobs.set_status(conn, job["id"], "running")
            await repo.videos.set_status(conn, video["id"], "uploading")
            await record_event(
                conn, "upload_started", message=f"{publisher.mode} publish started",
                channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
                data={"mode": publisher.mode},
            )

    chat_id = approval.get("telegram_chat_id")
    msg_id = approval.get("telegram_message_id")

    if decision == "reject":
        if msg_id:
            await notifier.update_resolved(
                chat_id=chat_id, message_id=msg_id,
                text=f"❌ <b>Rejected</b> by {decided_by}\n<b>{video['title']}</b> — not published.",
            )
        return {"handled": True, "decision": "reject", "job_id": job["id"]}

    if publisher.mode == "live" and msg_id:
        await notifier.update_resolved(
            chat_id=chat_id, message_id=msg_id,
            text=f"⏳ <b>Approved</b> — uploading <b>{video['title']}</b> to YouTube (private)…",
        )

    # --- Phase 2: the publish — NO DB transaction held ---
    try:
        result = await publisher.publish(video, channel)
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
                text=f"⚠️ <b>Upload failed</b>\n<b>{video['title']}</b>\n<code>{e}</code>",
            )
        return {"handled": True, "decision": "approve", "job_id": job["id"], "error": str(e)}

    # --- Phase 3: persist the result (txn) ---
    async with conn.transaction():
        await repo.videos.set_published(
            conn, video["id"], youtube_video_id=result.youtube_video_id,
            privacy_status=result.privacy_status, published_at=result.published_at,
            status=result.video_status,
        )
        # A real upload SETS the description at insert, so the authored version is now live — record
        # that truthfully. (Dry-run applies nothing; the version stays authored-but-not-live.)
        if result.mode == "live":
            meta = await repo.metadata.get_latest_authored(conn, video["id"])
            if meta is not None and meta.get("applied_at") is None:
                await repo.metadata.mark_applied(
                    conn, meta["id"], applied_at=result.published_at, applied_via="upload_insert"
                )
        await repo.jobs.set_status(conn, job["id"], result.job_status, result=result.to_dict())
        ev_type = "published" if result.mode == "live" else "dry_run_published"
        ev_msg = ("published PRIVATELY to YouTube" if result.mode == "live"
                  else "DRY RUN — would publish (no real upload)")
        await record_event(
            conn, ev_type, message=ev_msg, channel_id=channel["id"], job_id=job["id"],
            approval_id=approval["id"], data=result.to_dict(),
        )

    if msg_id:
        await notifier.update_resolved(
            chat_id=chat_id, message_id=msg_id, text=_resolved_text(video, result, decided_by)
        )
    return {
        "handled": True, "decision": "approve", "job_id": job["id"],
        "video_id": video["id"], "result": result.to_dict(),
    }


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

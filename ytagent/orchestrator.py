"""The conductor. Composes repo + events + publish + budget + a Notifier into the
submit -> approve/reject -> dry-run-publish flow. Depends on the Notifier PROTOCOL, never on
python-telegram-bot (so the dashboard can drive the same flow later). Every state change is
recorded through ytagent.events.record_event.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import repo
from .budget import budget_status
from .events import record_event
from .publish import dry_run_publish

if TYPE_CHECKING:  # avoid importing the transport at runtime
    from .notifier import Notifier


def _fmt_num(v: Any, suffix: str = "", nd: int = 1) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return f"{v}{suffix}"


def _format_approval_text(video: dict, channel: dict, budget: dict) -> str:
    dur = video.get("duration_s")
    mins = f"{int(dur) // 60}:{int(dur) % 60:02d}" if dur else "—"
    size_mb = f"{video['size_bytes'] / 1_000_000:.1f} MB" if video.get("size_bytes") else "—"
    return (
        f"🎬 <b>Approval needed — publish</b>\n"
        f"Channel: <b>{channel['name']}</b>\n"
        f"Title: <b>{video['title']}</b>\n\n"
        f"Duration: {mins} ({_fmt_num(dur, 's')})  •  "
        f"{video.get('width','?')}×{video.get('height','?')} @ {_fmt_num(video.get('fps'),'fps',0)}\n"
        f"Loudness: {_fmt_num(video.get('loudness_lufs'),' LUFS')}  •  "
        f"Peak: {_fmt_num(video.get('peak_dbfs'),' dBFS')}  •  "
        f"Noise floor: {_fmt_num(video.get('noise_floor_db'),' dB')}\n"
        f"File: {size_mb}\n"
        f"Provenance: <code>{video.get('provenance_ref') or '—'}</code>\n\n"
        f"💷 Month-to-date spend: <b>£{budget['month_spend_gbp']:.2f}</b> "
        f"/ £{budget['ceiling_gbp']:.0f} ({budget['tier']})\n\n"
        f"⚠️ Publishing is a DRY RUN in this slice — no real upload."
    )


async def submit_video_for_approval(
    conn, notifier: "Notifier", *, channel: dict, video_meta: dict, chat_id: str
) -> dict:
    async with conn.transaction():
        job = await repo.jobs.create(
            conn, channel_id=channel["id"], type="publish", status="awaiting_approval",
            stage="publish", payload={"title": video_meta.get("title")},
        )
        video = await repo.videos.create(
            conn, channel_id=channel["id"], job_id=job["id"], status="awaiting_approval", **video_meta
        )
        approval = await repo.approvals.create(
            conn, channel_id=channel["id"], job_id=job["id"], kind="publish", telegram_chat_id=chat_id
        )
        await record_event(
            conn, "video_submitted", message=f"submitted '{video['title']}' for publish approval",
            channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"],
            data={"video_id": video["id"]},
        )

    budget = await budget_status(conn)
    text = _format_approval_text(video, channel, budget)
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
    conn, notifier: "Notifier", *, approval_id: int, decision: str, decided_by: str
) -> dict:
    state = "approved" if decision == "approve" else "rejected"
    result: dict | None = None

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

        if decision == "approve":
            result = dry_run_publish(video, channel)
            await repo.jobs.set_status(conn, job["id"], "published_dryrun", result=result)
            await repo.videos.set_status(conn, video["id"], "published_dryrun")
            await record_event(
                conn, "dry_run_published",
                message="DRY RUN — would publish (no real upload)",
                channel_id=channel["id"], job_id=job["id"], approval_id=approval["id"], data=result,
            )
        else:
            await repo.jobs.set_status(conn, job["id"], "rejected")
            await repo.videos.set_status(conn, video["id"], "rejected")

    if decision == "approve":
        val = result["validation"]
        resolved = (
            f"✅ <b>Approved</b> by {decided_by}\n"
            f"<b>{video['title']}</b> — DRY RUN published (no real upload).\n"
            f"privacyStatus: <code>{result['body']['status']['privacyStatus']}</code>  •  "
            f"synthetic-media disclosed: <code>true</code>\n"
            f"file check: {'✅ size matches' if val['size_matches'] else '⚠️ size mismatch'} "
            f"({val['size_bytes_actual']} bytes)"
        )
    else:
        resolved = f"❌ <b>Rejected</b> by {decided_by}\n<b>{video['title']}</b> — not published."

    if approval.get("telegram_message_id"):
        await notifier.update_resolved(
            chat_id=approval["telegram_chat_id"], message_id=approval["telegram_message_id"], text=resolved
        )

    return {
        "handled": True, "decision": decision, "job_id": job["id"],
        "video_id": video["id"], "result": result,
    }

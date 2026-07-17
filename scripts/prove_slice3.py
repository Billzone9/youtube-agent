"""LIVE proof of Slice 3 — assemble the lion master from on-disk assets and QC it vs the reference.

ZERO API spend (local FFmpeg only). Never touches the locked `_scored.mp4` — output is a NEW file.
  GATE: record_assembly → join the 7 pre-baked beats (xfade+acrossfade) → loudnorm → assembled.mp4,
        QC + VMAF vs the reference; the job-completion Telegram ping fires here.
  CAPABILITY (one beat each, not gating): Stage-1 raw→beat1 (16:9) vs beat1_v3 (QC+VMAF);
        general-audio rebuild of beat1 (loudness compare); a 9:16 render of beat1 (crop-to-format).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_slice3
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import orchestrator, repo
from ytagent.artifacts import lion_video_meta
from ytagent.assembly import qc, stage1, audio as audiomod
from ytagent.assembly.spec import load_spec
from ytagent.config import load_settings
from ytagent.notifier import StubNotifier

_SPEC = "lion-doc-01-edit-spec.json"
_OUT = "assets/lion-doc-01/output"
_SCORED = f"{_OUT}/lion-doc-01_scored.mp4"      # the LOCKED reference — read only, never written
_ASSEMBLED = f"{_OUT}/lion-doc-01_assembled.mp4"  # the NEW output


def _rule(w=80): print("─" * w)


def _print_qc(m: dict) -> None:
    print(f"  format {m['format']}  {m['width']}x{m['height']} @ {m['fps']}fps  "
          f"dur {m['duration_s']}s")
    print(f"  loudness {m['loudness_lufs']} LUFS  peak {m['peak_dbfs']} dBFS  "
          f"noise-floor(>8kHz) {m['noise_floor_db']} dB  size {m['size_bytes']:,}B")


async def _make_notifier(settings):
    """Real Telegram notifier if a token is set, else the stub (prints nothing external)."""
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


async def run() -> None:
    settings = load_settings()
    assert os.path.exists(_SCORED), f"locked reference missing: {_SCORED}"
    reference = lion_video_meta()   # QC target (width/height/fps/duration/loudness/peak)

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    notifier, bot = await _make_notifier(settings)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")

        print("=" * 80)
        print("(GATE) reproduce the lion master from the 7 pre-baked beats — vs the locked reference")
        print("=" * 80)
        res = await orchestrator.record_assembly(
            conn, notifier, channel=channel, spec_path=_SPEC, dst=_ASSEMBLED,
            chat_id=settings.chat_id, fmt="16:9", reference=reference,
            provenance_ref="lion-doc-01-footage-manifest.md",
        )
        if not res.get("ok"):
            print(f"  ASSEMBLY FAILED: {res.get('error')}")
            sys.exit(1)
        result = res["result"]
        print(f"\nassembled → {result.output_path}  (render {result.duration_render_s}s, "
              f"job #{res['job_id']} status 'assembled', video #{res['video_id']})")
        print("locked reference is untouched:", os.path.exists(_SCORED))
        _rule()
        print("QC of the assembled master:")
        _print_qc(result.qc)
        _rule()
        print("QC comparison vs reference:")
        for name, ok, detail in result.comparison.checks:
            print(f"  {'✅' if ok else '❌'} {name}: {detail}")
        print(f"  → QC {'PASS' if result.comparison.ok else 'FAIL'}")
        vscore = qc.vmaf(_ASSEMBLED, _SCORED, seconds=15)
        print(f"  VMAF vs _scored.mp4 (15s spot-check, SUPPLEMENTARY): {vscore}")
        print("  (same beats/content, but re-encoded + re-crossfaded, so not frame-aligned to the "
              "original encode — QC above is the gate; A/V review is the acceptance)")

        # ---- capability proofs (one beat each; cheap; not gating) ----
        spec = load_spec(_SPEC)
        beat1 = spec.beats[0]
        work = tempfile.mkdtemp(prefix="slice3-")

        print("\n" + "=" * 80)
        print("(CAP-A) Stage-1: build beat1 from RAW clips (16:9) — vs the baked beat1_v3")
        print("=" * 80)
        b1 = stage1.build_beat(spec.for_format("16:9"), beat1, os.path.join(work, "beat1_16x9.mp4"))
        m1 = qc.measure(b1)
        print(f"  raw→beat1: {m1['format']} {m1['width']}x{m1['height']}@{m1['fps']}fps "
              f"dur {m1['duration_s']}s (silent — Stage-1 is video-only; audio is CAP-B)")
        check_ok = (m1["width"], m1["height"], m1["fps"]) == (1920, 1080, 24)
        print(f"  → raw clips assembled into a valid 16:9 beat: {'✅' if check_ok else '❌'}")
        print("  (this is a FRESH edit from the raw clips — deliberately NOT a copy of the hand-tuned "
              "beat1_v3, so a VMAF match is not expected; it proves the clips→beat path works)")

        print("\n" + "=" * 80)
        print("(CAP-B) general audio: rebuild beat1's audio (narration + ducked music) — loudness")
        print("=" * 80)
        a1 = audiomod.rebuild_beat_audio(spec.for_format("16:9"), beat1,
                                         os.path.join(work, "beat1_audio.m4a"))
        lu, pk = qc.integrated_loudness(a1)
        print(f"  rebuilt beat1 audio: {lu} LUFS, peak {pk} dBFS (target -14) → "
              f"{'✅' if lu is not None and abs(lu + 14) <= 1.0 else 'check'}")

        print("\n" + "=" * 80)
        print("(CAP-C) multi-format: render beat1 as 9:16 (crop-to-format, Shorts-ready)")
        print("=" * 80)
        b169 = stage1.build_beat(spec.for_format("9:16"), beat1, os.path.join(work, "beat1_9x16.mp4"))
        m9 = qc.measure(b169)
        _print_qc(m9)
        print(f"  → 9:16 vertical: {'✅' if (m9['width'], m9['height']) == (1080, 1920) else '❌'}")

        print("\n" + "=" * 80)
        print(f"DONE. Gate QC {'PASS' if result.comparison.ok else 'FAIL'} · "
              f"VMAF {vscore} · assembled master at {_ASSEMBLED} (reference untouched).")
        if isinstance(notifier, StubNotifier):
            print(f"(stub notifier captured {len(notifier.notifications)} ping(s): "
                  f"{[n['text'] for n in notifier.notifications]})")
        print("=" * 80)
    finally:
        if bot is not None:
            await bot.shutdown()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

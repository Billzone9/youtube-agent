"""Regenerate the lion film's description to the public-facing standard, and record truthful history.

For the lion video (already uploaded PRIVATE under upload-only scope), this stores two authored
versions in video_metadata:
  * v1 = the ACTUAL live text — the leaked description currently on YouTube (source='legacy_artifact',
    applied_via='upload_insert', applied_at = the real publish time). We do not pretend v1 was clean.
  * v2 = the CLEAN regen authored to the standard (source='layer1_manual', applied_via=NULL — it is
    the latest authored version but NOT yet live; upload-only scope cannot push it to YouTube).

It then prints the exact clean block for Banks to paste into YouTube Studio. It does NOT call any
YouTube API and does NOT change the live video. Idempotent: re-running reports state and re-inserts
nothing. Run:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.regen_lion_description
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import repo
from ytagent.config import load_settings
from ytagent.metadata.guard import scan
from ytagent.metadata.lion_reference import build_lion_reference

_LION_FILE_MATCH = "%lion-doc-01_scored.mp4"


async def _find_lion(conn) -> dict | None:
    cur = await conn.execute(
        "SELECT * FROM videos WHERE file_path LIKE %s AND status = 'published' "
        "AND youtube_video_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        [_LION_FILE_MATCH],
    )
    return await cur.fetchone()


async def run() -> None:
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        video = await _find_lion(conn)
        if video is None:
            raise SystemExit("no published lion video found (expected the uploaded lion-doc-01).")
        vid = video["id"]
        print(f"lion video: #{vid}  youtube_id={video['youtube_video_id']}  "
              f"privacy={video['privacy_status']}  published={video['published_at']}")

        existing = await repo.metadata.list_versions(conn, vid)
        by_source = {r["source"] for r in existing}

        # v1 — the actual leaked text currently live (truthful history).
        if "legacy_artifact" not in by_source:
            leaked = video["description"] or ""
            v1 = await repo.metadata.create_version(
                conn, video_id=vid, channel_id=video["channel_id"], title=video["title"],
                description=leaked, tags=[], source="legacy_artifact",
                applied_at=video["published_at"], applied_via="upload_insert",
                research_notes={"note": "captured from the live video row — pre-standard leak"},
            )
            print(f"  stored v{v1['version']} = LEGACY live text (leaked), applied_via=upload_insert")
        else:
            print("  legacy_artifact version already present — skipping")

        # v2 — the clean regen, authored to the standard (latest authored, NOT yet live).
        if "layer1_manual" not in by_source:
            desc = build_lion_reference()   # assemble_description already ran the guard
            pub = desc.to_public_dict()
            v2 = await repo.metadata.create_version(
                conn, video_id=vid, channel_id=video["channel_id"], title=pub["title"],
                description=pub["description"], tags=pub["tags"], source="layer1_manual",
                research_notes={"research": "in-session web/trend (keyword-led opening; no youtube "
                                            "signals — upload-only scope)", "voice": "channel config"},
            )
            print(f"  stored v{v2['version']} = CLEAN regen (layer1_manual), applied_via=NULL "
                  "(not yet live)")
        else:
            print("  layer1_manual version already present — skipping")

        # Guard proof over both, straight from the DB.
        print("\nguard over stored versions:")
        for r in await repo.metadata.list_versions(conn, vid):
            hits = scan(r["title"], r["description"], *[str(t) for t in (r["tags"] or [])])
            verdict = "TRIPS -> " + "; ".join(hits) if hits else "clean ✅"
            print(f"  v{r['version']} [{r['source']:<15}] applied={'yes' if r['applied_at'] else 'no ':<3}"
                  f"  guard: {verdict}")

        # The exact clean block for Banks to paste in Studio.
        clean = await repo.metadata.get_latest_authored(conn, vid)
        print("\n" + "=" * 72)
        print("CLEAN DESCRIPTION FOR YOUTUBE STUDIO — copy the block between the lines")
        print("(the agent cannot apply it: OAuth is upload-only; the video is PRIVATE, so there is")
        print(" zero public exposure meanwhile. Future uploads are clean at insert.)")
        print("=" * 72)
        print(f"TITLE:\n{clean['title']}\n")
        print(f"DESCRIPTION:\n{clean['description']}\n")
        print(f"TAGS:\n{', '.join(clean['tags'])}")
        print("=" * 72)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

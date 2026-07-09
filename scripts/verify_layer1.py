"""Prove Layer 1 of the public-facing description standard against the DB.

Asserts:
  * the lion's latest authored version (clean regen) passes the guard;
  * the lion's legacy version (the actual leaked live text) TRIPS the guard on the manifest filename
    — i.e. the guard would have blocked the original leak (the strongest single proof);
  * video_metrics is empty but its Layer-2 fields are reserved;
  * build_youtube_body from the clean version yields a guard-clean snippet with authored SEO tags.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_layer1
"""
from __future__ import annotations

import sys

from ytagent.config import load_settings
from ytagent.db import sync_connect
from ytagent.metadata.guard import scan
from ytagent.publish import build_youtube_body

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def main() -> None:
    with sync_connect(load_settings()) as conn:
        video = conn.execute(
            "SELECT * FROM videos WHERE file_path LIKE %s AND status='published' "
            "AND youtube_video_id IS NOT NULL ORDER BY id DESC LIMIT 1",
            ["%lion-doc-01_scored.mp4"],
        ).fetchone()
        check("published lion video found", video is not None)
        if video is None:
            sys.exit(1)
        vid = video["id"]
        channel = conn.execute("SELECT * FROM channels WHERE id=%s", [video["channel_id"]]).fetchone()

        print(f"\nlion #{vid}  youtube_id={video['youtube_video_id']}  privacy={video['privacy_status']}")
        print("\nvideo_metadata versions:")
        versions = conn.execute(
            "SELECT version, source, applied_at, applied_via, title, description, tags "
            "FROM video_metadata WHERE video_id=%s ORDER BY version", [vid]).fetchall()
        legacy = clean = None
        for r in versions:
            hits = scan(r["title"], r["description"], *[str(t) for t in (r["tags"] or [])])
            live = "LIVE" if r["applied_at"] else "authored"
            print(f"  v{r['version']} [{r['source']:<15}] {live:<8} "
                  f"guard: {'clean' if not hits else 'TRIPS(' + hits[0] + ')'}")
            if r["source"] == "legacy_artifact":
                legacy = (r, hits)
            if r["source"] == "layer1_manual":
                clean = (r, hits)

        check("clean regen present + guard-clean", clean is not None and not clean[1])
        check("legacy (live leaked) version present", legacy is not None)
        if legacy is not None:
            check("guard TRIPS on the legacy leak (would have blocked it)", bool(legacy[1]),
                  legacy[1][0] if legacy[1] else "no hit")
        if clean is not None and legacy is not None:
            check("clean is the LATEST authored; leaked is what is LIVE",
                  clean[0]["applied_at"] is None and legacy[0]["applied_at"] is not None)

        # Layer-2 reservation: table empty, fields exist.
        m_n = conn.execute("SELECT count(*) n FROM video_metrics").fetchone()["n"]
        check("video_metrics empty (loop switches on with public data)", m_n == 0, f"{m_n} rows")
        cols = [r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='video_metrics'"
        ).fetchall()]
        reserved = {"impressions", "ctr", "views", "avg_view_duration_s", "subscribers_gained",
                    "search_terms", "period_start", "grain", "metadata_version_id"}
        check("Layer-2 metric fields reserved", reserved.issubset(set(cols)),
              f"missing {reserved - set(cols)}" if not reserved.issubset(set(cols)) else "")

        # A publish body built from the clean version is guard-clean and ships authored tags.
        if clean is not None:
            r = clean[0]
            vrow = {"title": r["title"], "description": r["description"], "tags": r["tags"],
                    "primary_language": "en"}
            body = build_youtube_body(vrow, channel)   # raises if it would leak
            snip = body["snippet"]
            check("clean build_youtube_body snippet is artifact-free", not scan(snip["description"]))
            check("authored SEO tags reach the snippet", "lion documentary" in snip["tags"],
                  str(snip["tags"][:4]))
            print(f"\n  snippet.title: {snip['title']}")
            print(f"  snippet.tags:  {', '.join(snip['tags'])}")
            print(f"  snippet.description (first line): {snip['description'].splitlines()[0]}")

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    main()

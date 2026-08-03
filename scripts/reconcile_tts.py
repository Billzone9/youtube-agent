"""Settle the outstanding ElevenLabs TTS ledger rows against the authoritative per-call history — the
one source that converts TTS from ESTIMATED to SETTLED permanently (B3, decision 2). Needs the
`speech_history_read` permission on the key (read-only). Music is NOT in history, so it still needs the
balance-delta; this handles TTS only.

Matching: each cost_ledger TTS row stores metadata.request_id (the TTS response's request-id) and its
exact `characters`. History items carry request_id + the character-count delta. We match on request_id
first, then fall back to (characters within a small time window) for rows whose request_id predates the
history retention or didn't round-trip. TTS is char-exact, so settled ≈ estimate — the point is to mark
the rows reconciled=true with real evidence, so estimate_vs_actual can show a MEANINGFUL ratio.

Run (dry-run):  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.reconcile_tts
Run (apply):    ... ./.venv/bin/python -m scripts.reconcile_tts --commit
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent.audio_design import _GBP_PER_CREDIT
from ytagent.config import load_settings

_HIST = "https://api.elevenlabs.io/v1/history"


def _fetch_history(key: str) -> list[dict] | None:
    """All TTS history items (paginated). None if the key lacks speech_history_read (401)."""
    items, page_key, h = [], None, {"xi-api-key": key}
    with httpx.Client(timeout=60) as c:
        for _ in range(200):                          # hard page cap
            params = {"page_size": 100}
            if page_key:
                params["start_after_history_item_id"] = page_key
            r = c.get(_HIST, headers=h, params=params)
            if r.status_code == 401:
                print("  ✗ 401 missing_permissions — the key still lacks 'speech_history_read'.")
                print("    Add it in the ElevenLabs dashboard (see below), then re-run.")
                return None
            r.raise_for_status()
            d = r.json()
            batch = d.get("history", [])
            items.extend(batch)
            if not d.get("has_more") or not batch:
                break
            page_key = batch[-1].get("history_item_id")
    return items


def _settled_chars(item: dict) -> int:
    delta = int(item.get("character_count_change_to", 0)) - int(item.get("character_count_change_from", 0))
    return delta if delta > 0 else len(item.get("text", "") or "")


async def run():
    commit = "--commit" in sys.argv
    settings = load_settings()
    key = os.environ.get("ELEVENLABS_API_KEY") or settings.elevenlabs_api_key
    print(f"=== TTS settlement {'(COMMIT)' if commit else '(dry-run)'} ===")
    hist = await asyncio.to_thread(_fetch_history, key)
    if hist is None:
        sys.exit(2)
    by_req = {i.get("request_id"): i for i in hist if i.get("request_id")}
    print(f"  history items fetched: {len(hist)} ({len(by_req)} with a request_id)")

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    rows = await (await conn.execute(
        "SELECT id, credits, metadata FROM cost_ledger WHERE provider='ElevenLabs TTS' "
        "AND reconciled=false")).fetchall()
    print(f"  unreconciled TTS rows: {len(rows)}")

    settled, unmatched = 0, 0
    for row in rows:
        rid = (row["metadata"] or {}).get("request_id")
        item = by_req.get(rid)
        if item is None:                              # request_id didn't match a retained history item
            unmatched += 1
            continue
        chars = _settled_chars(item)
        gbp = round(chars * _GBP_PER_CREDIT, 4)
        settled += 1
        if commit:
            meta = {**(row["metadata"] or {}), "estimate": False, "settled": True,
                    "history_item_id": item.get("history_item_id"), "settled_chars": chars}
            await conn.execute(
                "UPDATE cost_ledger SET reconciled=true, credits=%s, amount_gbp=%s, metadata=%s WHERE id=%s",
                [chars, gbp, Jsonb(meta), row["id"]])

    print(f"  matched + {'SETTLED' if commit else 'would settle'}: {settled}")
    print(f"  unmatched (request_id not in history retention): {unmatched}")
    if not commit and settled:
        print("  → re-run with --commit to write reconciled=true. Then estimate_vs_actual shows a real TTS ratio.")
    print("  NOTE: music has NO per-call history — it still needs the guarded balance-delta reconciler.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

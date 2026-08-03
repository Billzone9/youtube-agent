"""Settle the outstanding ElevenLabs TTS ledger rows against the authoritative per-call history — the
one source that converts TTS from ESTIMATED to SETTLED permanently (B3, decision 2). Needs the
`speech_history_read` permission on the key (read-only). Music is NOT in history, so it still needs the
balance-delta; this handles TTS only.

Matching: each cost_ledger TTS row stores metadata.request_id (the TTS response's request-id) and its
exact `characters`. History items carry request_id + the character-count delta. We match on request_id
FIRST; then a real FALLBACK — a history item with the SAME character count within a time window of the
row's incurred_at, used only if that (chars, window) pick is UNIQUE (ambiguous or missing → reported,
not guessed). The fallback matters because (a) history's request_id may not equal our stored response-id
and (b) older items may be past history retention. TTS is char-exact, so settled ≈ estimate — the point
is to mark the rows reconciled=true with REAL evidence, so estimate_vs_actual can show a MEANINGFUL ratio.

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


_FALLBACK_WINDOW_S = 3 * 24 * 3600     # async settlement can lag; ±3 days around the row's incurred_at


def _settled_chars(item: dict) -> int:
    delta = int(item.get("character_count_change_to", 0)) - int(item.get("character_count_change_from", 0))
    return delta if delta > 0 else len(item.get("text", "") or "")


def _fallback_match(row_chars: int, row_ts: int, hist: list[dict], used: set) -> dict | None:
    """A history item with the SAME char count within the window of the row — only if UNIQUE. Ambiguous
    (>1 candidate) or none → return None so the caller reports it rather than mis-attributing."""
    cands = [it for it in hist
             if it.get("history_item_id") not in used
             and _settled_chars(it) == row_chars
             and abs(int(it.get("date_unix", 0)) - row_ts) <= _FALLBACK_WINDOW_S]
    return cands[0] if len(cands) == 1 else None


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
        "SELECT id, credits, metadata, (metadata->>'characters')::int chars, "
        "extract(epoch from incurred_at)::bigint ts FROM cost_ledger WHERE provider='ElevenLabs TTS' "
        "AND reconciled=false AND job_id IS NOT NULL")).fetchall()   # real production rows only (skip test junk)
    print(f"  unreconciled production TTS rows: {len(rows)}")

    by_req_c, by_fallback, unmatched = 0, 0, 0
    used: set = set()
    for row in rows:
        rid = (row["metadata"] or {}).get("request_id")
        item = by_req.get(rid)
        method = "request_id"
        if item is None:                              # request_id miss → try the (chars, time-window) fallback
            item = _fallback_match(row["chars"] or 0, row["ts"] or 0, hist, used)
            method = "chars+window"
        if item is None:
            unmatched += 1
            continue
        used.add(item.get("history_item_id"))
        chars = _settled_chars(item)
        gbp = round(chars * _GBP_PER_CREDIT, 4)
        by_req_c += method == "request_id"
        by_fallback += method == "chars+window"
        if commit:
            meta = {**(row["metadata"] or {}), "estimate": False, "settled": True, "settle_method": method,
                    "history_item_id": item.get("history_item_id"), "settled_chars": chars}
            await conn.execute(
                "UPDATE cost_ledger SET reconciled=true, credits=%s, amount_gbp=%s, metadata=%s WHERE id=%s",
                [chars, gbp, Jsonb(meta), row["id"]])

    settled = by_req_c + by_fallback
    print(f"  matched + {'SETTLED' if commit else 'would settle'}: {settled}  "
          f"(by request_id: {by_req_c}, by chars+window fallback: {by_fallback})")
    print(f"  unmatched (past history retention or ambiguous chars): {unmatched}")
    if not commit and settled:
        print("  → re-run with --commit to write reconciled=true. Then estimate_vs_actual shows a real TTS ratio.")
    print("  NOTE: music has NO per-call history — it still needs the guarded balance-delta reconciler.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

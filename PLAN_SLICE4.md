# Slice 4 — Asset sourcing (claim-safe footage from Pexels/Pixabay, gated + provenance-logged)

## Context
The script writer (Slice 5) emits per-beat **shot-briefs** — free-text prose describing the visuals a
video needs (`ytagent/authoring/script.py` `Beat.shot_brief`). Slice 4 turns those briefs into real,
claim-safe footage on disk: search Pexels + Pixabay (free tier), rank candidates by written metadata +
licence, download matches, run every download through the **Slice-3 input noise/QC gates** (a dirty or
broken download NEVER enters a production), log full provenance per asset (URL, contributor, licence,
timestamp — never fabricated), and cache so the same asset is never re-fetched. Channel-general.
Autonomous (no per-asset gate — Banks reviews the finished VIDEO; that review is the quality gate).
The proof: source real footage for the emperor-penguin script's 5 shot-briefs (from `PROOF_SLICE5.md`).

## Keys & the human step (flag for Banks)
- Add optional `pexels_api_key` / `pixabay_api_key` to `Settings` (like `anthropic_api_key`);
  `safe_summary()` shows `pexels_configured`/`pixabay_configured` bools, never the key.
- **Banks creates both keys, scoped free-tier, NO payment method attached** — a footage key
  structurally *cannot* spend (CLAUDE.md "what the key CAN'T do"). Until they exist,
  `get_stock_providers()` returns `[]` and the slice degrades honestly (the offline proof still runs).
- Downloads are **free** — the only spend in the slice is the pennies of Haiku query-extraction.

## Architecture — `ytagent/sourcing/` (async; mirrors `ytagent/providers/`)
- **`base.py`** — `StockProvider` Protocol (`name`, `healthcheck`, `search(query,*,orientation,
  min_duration,per_page)`, `rate_limit`), frozen `Candidate` and `QueryPlan`, `SourcingError`.
  `Candidate{source, asset_id, page_url (authoritative → the provenance URL), download_url (chosen
  rendition ≥ target res), contributor, licence, width, height, duration, fps, orientation, title,
  tags, raw (verbatim API record)}`.
- **`pexels.py` / `pixabay.py`** — concrete providers (`httpx.AsyncClient`; key from config: Pexels
  `Authorization` header, Pixabay key as query param). Each normalizes API results to `Candidate`,
  **selecting the smallest `video_files` rendition ≥ target** as `download_url` (resolution is a
  rendition SELECTION, not a candidate filter).
- **`factory.py`** — `get_stock_providers(settings) -> list[StockProvider]` (only keyed providers;
  `[]` ⇒ caller degrades honestly, exactly like `get_llm_provider → None`).
- **`query.py`** — `build_query_plan(brief, *, approx_seconds, target_fmt, llm) -> QueryPlan`:
  **orientation** = `{16:9→landscape, 9:16→portrait}[fmt]` and **min_seconds** = `approx_seconds` are
  DETERMINISTIC (already authoritative in code — never ask the LLM for them). **queries**: one CHEAP
  (Haiku) call via the Slice-5 `providers` layer extracting 2-4 concrete search phrases from the
  brief (stage directions stripped with `authoring/script._STAGE_DIR`); deterministic `_keywords`
  fallback (drop camera/stopwords, keep subject bigrams) when `llm is None`. LLM spend lands in
  `cost_ledger` (category `ai_generation`) via `ListUsageSink`, idempotently — the ONLY spend.
- **`rank.py`** — `score_candidate` / `rank_candidates`, `MATCH_THRESHOLD = 0.35`. Metadata-only
  score: **keyword overlap** (query terms vs candidate `tags + title + url-slug`, NOT contributor)
  0.45 + **orientation match** 0.30 + **duration adequacy** 0.15 + **resolution adequacy** 0.10.
  Tie-break: source diversity → higher res → longer.
- **`download.py`** — `download(candidate, dst_dir)`: atomic `.part` → `os.replace`, with a
  `Content-Length`-vs-bytes size check (truncation guard).
- **`gate.py`** — `gate_download(path, *, orientation, min_seconds) -> GateResult`: `ffmpeg.probe`
  (raises on a corrupt/undecodable file) + a decode pass + orientation check + duration/truncation
  check, and **`qc.check_source_clean` ONLY when `probe()["has_audio"]`** — a no-audio clip PASSES the
  noise gate by construction (stock footage is usually silent; the assembler supplies narration/music).
  **This silent-clip branch is the #1 thing to get right** — a naïve noise gate rejects every clean
  silent clip.
- **`provenance.py`** — `build_asset_provenance(candidate, gate, path)` → the **LOGGED** record from
  the authoritative API fields (`url=page_url`, `contributor`, `licence`, `downloaded_at`, `raw`),
  `provenance_source='logged'` — never derived, never fabricated; missing contributor flagged
  "(see page)". INTERNAL record only (the `metadata/guard.py` net keeps asset IDs/URLs/`manifest`
  tokens out of public text — structural separation).
- **`orchestrator.py`** — `source_for_brief(...) -> SourcedAsset | NoMatch` and
  `source_shot_briefs(...) -> list[SourcedAsset | NoMatch]`. Flow: build query plan → search all
  providers × queries → rank → **download top-K (K=3) in rank order → gate → first clean winner
  wins** (cache + provenance-log only the winner). If the best score `< MATCH_THRESHOLD`, results are
  empty, or all K fail the gate → **`NoMatch` (fail loudly — NEVER pad with a bad clip)**, surfaced 3
  ways: the return object, an `events` row (`sourcing.no_match`), and the CLI line.
- **`ytagent/repo/sourcing.py`** — async SQL for `sourced_assets` (mirrors `repo/ledger.py`):
  `get_by_asset(source, asset_id)`, `upsert(...)`.

## Caching (never re-fetch)
- Cache dir `assets/sourced/{source}/{asset_id}.{ext}` (channel-general, under the gitignored `assets/`).
- DB row keyed by `idempotency_key = f"{source}:{asset_id}"` (plain-unique → `ON CONFLICT` infers it).
- **Lookup-before-fetch:** if a row exists AND `os.path.exists(local_path)` → return
  `SourcedAsset(cached=True)` with NO network call. A permanent asset cache is strictly stronger than
  Pixabay's 24h-cache ToS (we never re-hit).

## Data model — migration `0005_sourcing.sql`
`sourced_assets` (0001/0003 conventions: bigint identity PK + `public_id uuid` + timestamptz +
text/CHECK + jsonb + plain-unique idempotency + `set_updated_at` trigger), keyed by `channel_id` +
optional `job_id`: `source CHECK(pexels|pixabay)`, `asset_id`, `url`, `contributor`, `licence`,
`provenance_source CHECK(logged|derived) DEFAULT logged`, `local_path`, `width/height/duration_s/fps/
orientation CHECK(landscape|portrait|square)`, `title`, `tags jsonb`, `size_bytes`, `checksum` sha256,
`gate_pass bool`, `gate_report jsonb`, `shot_brief_ref`, `query_used`, `api_response jsonb` (verbatim
record → provenance recoverable without re-fetch), `idempotency_key`. (`cost_ledger` already has the
`stock_media` category — no schema change for spend, and downloads are free.)

## The honest hard limit (state it plainly)
Metadata gives duration/format/tags/title — **NOT what the footage actually looks like**. So ranking
is metadata-only (keyword/orientation/duration/resolution), and Pexels video metadata is THIN (little
more than a URL slug + `alt`; keyword overlap is strong for Pixabay, weak for Pexels — honest limit).
"No good match" (below threshold / empty / all top-K gate-fail) **fails loudly per shot-brief and is
never padded with a bad clip**; the run completes with the gap flagged. **Banks's review of the
finished video remains the quality gate.**

## Rate limits + the Pexels-403 reality
- Pexels ~200 req/hr + 20k/mo; Pixabay ~100 req/min + 24h-cache ToS — handled structurally by
  cache-first + polite `429` backoff + `rate_limit()` surfaced to `events` (`sourcing.search`).
- The confirmed HTTP 403 was **pexels.com (the website)**; `api.pexels.com` with an auth key is a
  different endpoint that MAY answer from this IP. `PexelsProvider.healthcheck()` does one tiny
  authenticated probe up front; an unavailable provider is **dropped from the pool** (honest
  degradation) with the verdict logged. **If authenticated Pexels 403s from the Mac's IP, Pixabay
  carries the proof** (real tags → the ranker works well), and Pexels is **designed-but-deferred-to-
  the-VPS/another network** — fully written + tested against the fake, waiting only for a network
  where the API answers. No VPS work in this slice.

## Downstream tie-in (seam only)
`to_clip(SourcedAsset, *, approx_seconds) -> assembly.spec.Clip` (`src`=cached path, `trim_out`=min(
duration, approx_seconds), `focus` centre default; orientation already gate-guaranteed to match the
target). **Deferred to a later slice:** the full script→`EditSpec` binder (the
`ScriptWriter.write(footage=…)` seam that currently raises). Slice 4 stops at sourced assets +
a `brief_ref → SourcedAsset|NoMatch` mapping.

## Files
**New:** `ytagent/sourcing/{__init__,base,pexels,pixabay,factory,query,rank,download,gate,provenance,
orchestrator}.py`; `ytagent/repo/sourcing.py`; `ytagent/migrations/0005_sourcing.sql`;
`scripts/verify_slice4.py` (offline, zero network); `scripts/prove_slice4.py` (live, gated behind keys).
**Edited (light):** `ytagent/config.py` (optional pexels/pixabay keys + `*_configured`);
`ytagent/repo/__init__.py` (export sourcing); `.env.example` (PEXELS_API_KEY/PIXABAY_API_KEY);
`telegram_bot/requirements.txt` (add `httpx` — already in the venv, pin it for the container).

## Verification
- **Offline (`scripts/verify_slice4.py`, zero network, always runnable, ZERO spend):** a
  `FakeStockProvider` returns canned candidates (a high-score match, a wrong-orientation low-scorer,
  and an EMPTY brief to prove `NoMatch`). Real gate exercised on two `ffmpeg lavfi`-generated scratch
  clips: a **clean SILENT** clip (proves the no-audio branch PASSES) and a **hissy** clip (proves the
  noise gate REJECTS → orchestrator falls through to the next candidate). Asserts: deterministic query
  fallback (no LLM), ranking order + threshold, fail-loud `NoMatch`, gate reject→next→winner, **cache
  hit on a second call** (row+file ⇒ no fetch), provenance record = `logged` with authoritative
  fields, and `guard.scan()` clean (provenance never leaks to public text). ALL PASSED.
- **Live (`scripts/prove_slice4.py`, gated behind the keys, Banks's go):** source the 5 penguin
  shot-briefs (target 16:9 → landscape). Per brief prints the chosen clip (cached path + provenance
  url/contributor/licence/timestamp + gate pass with probe numbers) OR `"NO GOOD MATCH — failed
  loudly"`. A second run demonstrates the cache (0 network). Zero LLM spend beyond the cheap Haiku
  query extraction (~a penny for 5 briefs; £0 with the deterministic fallback). Existing Slice
  1/Layer 1/Slice 3/Slice 5 verifies stay green.

## Expensive-to-retrofit (locked)
1. **`sourced_assets` schema completeness** — `api_response` (verbatim), `checksum`+`size_bytes`,
   `provenance_source` enum, `orientation`, `idempotency=source:asset_id`. Backfill later needs a re-fetch.
2. **The `Candidate` normalization contract** (`page_url` vs rendition `download_url`, `orientation`,
   `raw`) — the one interface ranker/gate/provenance depend on.
3. **Gate = `has_audio` branch** (skip `check_source_clean` on silent clips) + atomic size-checked
   download. Get wrong ⇒ every clean stock clip rejected as "dirty".
4. **Fail-loud as a return TYPE** (`SourcedAsset | NoMatch`, never pad) — callers + the future binder
   depend on it being explicit, not a silent substitution.
5. **Cache key + dir layout** (`source:asset_id`, `assets/sourced/{source}/{id}.ext`) — idempotency +
   ToS compliance; changing it orphans the cache and re-hits the APIs.
6. **Provenance = LOGGED-not-derived, wired to authoritative API fields + guard separation.**
7. **`StockProvider` Protocol + factory-returns-`[]` + Pexels `healthcheck` preflight** — a 403'd IP
   or missing key degrades cleanly (mirrors `get_llm_provider → None`).

## Deliberately NOT in this slice
Audio/SFX sourcing (footage only — no music from these sites, Content ID); generative-video fallback
for shots stock can't provide (spec's cost-gated AI B-roll — later); the script→`EditSpec` binder
(`ScriptWriter.write(footage=…)`); regenerating the `.md` manifest each run (DB is the source of
truth; a manifest export is a trivial read-model later); a separate TTL search-cache (the permanent
asset cache satisfies the ToS); logging free downloads to `cost_ledger` (£0 rows are noise — use `events`);
per-asset approval (autonomous — Banks reviews the finished video); any VPS work.

## Conventions / safety
Channel-general (nothing niche in code). Add only this slice's stack (`httpx`, already present).
Secrets via `.env`, never printed/committed. **Never fabricate a URL.** No music from these sites. A
dirty/broken/no-match source fails loudly — never pad. Build/prove on the Mac; never touch the VPS or
ocean stream. Commit locally; push only on the ship-word. Tag command blocks `[ON YOUR MAC]`; no `#`
lines in shell blocks; end chains with `&& echo "OK..." || echo "FAILED..."`.

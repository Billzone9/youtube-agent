# Slice 5 — The autonomous LLM writer (descriptions + footage-led scripts)

## Context
The agent has produced public text only from **hand-authored** references so far (the locked lion
description in `ytagent/metadata/lion_reference.py`; the lion script/narration authored by Banks and
me). Slice 5 makes the agent write for itself: generate **YouTube descriptions** (to the
public-facing standard, §15) **and footage-led narration scripts**, in the established house voice,
per channel. Layer 1 deliberately left the seams open — `Writer` and `generate_description` raise
rather than fabricate — and this slice fills them. The test that matters is Banks reading a
description and a script the agent wrote *itself* and judging whether they hit the house voice with
**no AI tells**.

Provider is **locked to the direct Claude API** behind a **swappable** internal interface (spec §4.4:
one interface, Claude now, others addable later). Banks creates a **scoped, capped** Anthropic key the
safe way (same structural model as the ElevenLabs key); the agent never touches billing.

## Provider decision & the key (human step — flag for Banks)
- **Anthropic direct**, SDK `anthropic`. Model IDs: Haiku `claude-haiku-4-5-20251001` (routine/cheap:
  tags, classification), Sonnet `claude-sonnet-4-6` (quality prose: descriptions, scripts), Opus
  `claude-opus-4-8` (**wired but unused** — reserved for where it measurably earns it; nothing in
  Slice 5 earns it).
- **BANKS creates the key** — scoped to the Anthropic API, with a hard spend cap, added to `.env` as
  `ANTHROPIC_API_KEY` the safe way. Adding the key / raising the cap stays a **manual, human-only**
  action. The agent reads it from `.env`, never prints/logs/commits it.
- Honest degradation: no key ⇒ `get_llm_provider()` returns `None` ⇒ the writer stays `NullWriter`
  (raises, never fabricates), exactly as Layer 1.

## Architecture — three layers, cleanly separated
**A) `ytagent/providers/` — the swappable LLM interface (no DB, no niche).**
- `base.py` — pure types: `ModelTier` enum (`CHEAP`/`QUALITY`/`PREMIUM`), `CacheableBlock(text, cache)`,
  `LLMRequest(tier, system: tuple[CacheableBlock], messages, max_tokens, purpose, batch, channel_id,
  job_id)`, `TokenUsage(input, output, cache_creation, cache_read)`, `LLMResponse(text, model, usage,
  request_id, stop_reason, batch_id)`, `LLMProvider` Protocol (`complete`, `submit_batch`,
  `retrieve_batch`), `UsageSink` Protocol.
- `anthropic_provider.py` — the one concrete impl. Owns the **tier→model-id map** (routing lives here,
  not at call sites), the sync `anthropic.Anthropic()` client, and `count_tokens` for estimates.
  Per the claude-api skill: use `messages.create`; **do not** send `temperature`/`top_p`/`budget_tokens`/
  trailing-assistant prefill (they 400 on Sonnet 4.6 / Opus 4.8). Pushes a usage record to the injected
  `UsageSink` after each call — the provider itself never writes the DB.
- `pricing.py` — `usage_to_gbp(model, usage)` from `platform_settings` prices; four buckets
  (input full, output full, cache_read ≈0.1×, cache_creation ≈1.25×) then USD→GBP FX.
- `__init__.py` — `get_llm_provider(settings, usage_sink) -> LLMProvider | None` factory (reads
  `LLM_PROVIDER`, default `anthropic`; `None` when the key is absent).

**B) `ytagent/authoring/` — the house voice + script machinery (channel-general).**
- `style.py` — `POSITIVE_REGISTER` (channel-general craft: write to the footage; concrete image over
  abstraction; fact-underneath discipline; earn cadence, don't manufacture it), `BANNED_TICS` (the
  explicit, extensible negative list), `STYLE_SPEC_VERSION`, and `compose_style(voice_brief, exemplars)
  -> StyleSpec`. **The lion voice enters ONLY as data** — the channel `VoiceBrief` (from config) + the
  channel's registered **exemplar files** (few-shot, cacheable). Nothing wildlife-specific in code.
- `tells.py` — `scan_tells(text) -> TellReport`. **FLAGS, never mutates** (kept out of `guard.py`,
  which is a hard publish-gate on internal-artifact leaks — a different concern). Heuristics
  **calibrated to the lion's own baseline**, because the lion is deliberately dense with em-dashes and
  tricola — those are the house voice, not tells:
  - em-dash density per 100 words — flag only **above** the lion narration's measured density.
  - exclamation marks — lion uses zero → flag any.
  - `not only … but also` scaffold — flag each (lion never uses it).
  - generic explainer openers (opening only): "in this video", "we'll explore", "let's dive in",
    "have you ever wondered", "welcome back", "today we're going to".
  - LLM lexical crutches (advisory counts): "delve", "tapestry", "testament to", "nestled",
    "in conclusion", "it's important to note", "ultimately".
  - rule-of-three density — **report as a number, do NOT gate** (the house voice uses tricola).
  - **Acceptance test:** `scan_tells(lion-doc-01-narration.md).flagged == False`. If it flags the lion,
    the thresholds are wrong, not the lion.
- `script.py` — `ScriptWriter` + frozen `Script(title, runtime_target_s, word_target,
  beats: list[Beat], facts_used: list[Fact], provenance)`, `Beat(index, label, shot_brief, vo,
  approx_seconds)`, `Fact(claim, established: bool)`, `Script.to_narration() -> dict[str,str]`
  (strips stage directions to clean per-beat prose — reproduces the `script.md → narration.md`
  relationship in code). I/O: `write(topic, channel, research, style, footage=None) -> Script`.
  **Ship only the `footage=None` path**: the visual direction per beat is a **shot-brief (output)**
  that Slice 4 sourcing will later fulfil — the script is footage-led in *form* without pretending
  footage exists. The `footage` param is the visible seam for Slice 4; **no binder built now**.

**C) `ytagent/metadata/` — fill the description seam (minimal change).**
- `llm_writer.py` (new) — `LLMWriter` implementing the existing `Writer` Protocol
  (`write(*, video, channel, research) -> {title, opening, chapters, disclosure, tags}`). Neutral name
  (provider injected — §4.4 swappable). Builds system blocks from `authoring.style` + the injected
  `LLMProvider`; QUALITY call for prose (title/opening/disclosure), CHEAP call for tags; runs
  `scan_tells` on the opening and regenerates on flag (up to N). Flows through the **unchanged**
  `generate_description → assemble_description → guard` path, so an LLM-emitted artifact hard-fails on
  the existing net (the regression proof). **Not imported in `metadata/__init__.py`** (lazy import
  where used, to avoid an import cycle with `authoring`).
- `description.py` — the **one** change: make `chapters` **optional** in `assemble_description`
  (omit ⇒ `opening → disclosure`, no Chapters block). Doctrine §2 licenses "chapters *where the
  content supports them*". A brand-new topic has no cut, so no honest timestamps exist — the writer
  authors **labels only, over real timestamps it is given**, and **never generates timestamps**
  (accuracy/honesty invariant). The lion (real 6:34 cut) keeps its real chapters; a new-topic
  description omits them until Slice 3 assembly binds real per-beat starts.

## Cost accounting — write actuals, estimate advisory, NO enforcement
- **No migration.** `ai_generation` is already in the `cost_ledger` category CHECK; USD→GBP fits the
  existing `currency`/`amount_original`/`fx_rate`/`fx_rate_date` columns; per-version model provenance
  fits `video_metadata.research_notes` (jsonb).
- **Provider is DB-free.** It pushes token usage to an injected `UsageSink`; the **async orchestrator/
  runner drains the sink** and writes the ledger on the async connection (keeps DB off the sync writer
  seam).
- `repo/ledger.py` gains `write_llm_cost(...)` mirroring `seed._upsert_cost`: `category='ai_generation'`,
  `channel_id`, `job_id`, `provider='Anthropic'`, `description=f"LLM {purpose} ({model})"`,
  `amount_original`=USD, `currency='USD'`, `fx_rate`/`fx_rate_date`, `amount_gbp`=USD×FX,
  `period_month`, `reconciled=True`, `idempotency_key=f"llm:{request_id}"` (plain-unique; NULLs
  distinct), `metadata={input,output,cache_read,cache_creation,tier,purpose}`. `ON CONFLICT
  (idempotency_key) DO UPDATE`. `month_to_date_cost_gbp` already sums `amount_gbp`, so USD storage is
  transparent — no budget-view change.
- **Prices + FX as DATA** in `platform_settings` (`key='llm_pricing'`), seeded by `seed.py`,
  dashboard-controllable — not code constants.
- **Advisory estimate only:** before a call, `count_tokens` × input price + budgeted output ⇒
  `record_event("llm_cost_estimate", data={...})` alongside `budget_status().remaining_gbp`.
  **No ceiling enforcement** — that is §4.10's own slice; enforcing here would duplicate it and could
  silently kill generation.
- **Batch reconciliation (async settlement, ElevenLabs-style):** at `submit_batch` write nothing (or a
  `reconciled=false` estimate keyed `batch:{batch_id}:{custom_id}`); at `retrieve_batch` each result
  carries its own usage ⇒ write the actual with `reconciled=True`, same key, `ON CONFLICT DO UPDATE`.

## Prompt caching & batch
- **Cache prefix order (stable → volatile), cache marker on the LAST stable block** (≤4 breakpoints):
  house-style spec (global, byte-identical) → reference exemplar(s) (per-channel) → per-channel voice
  brief (**ephemeral**) → *(scripts only)* footage manifest (ephemeral) → messages: this video's facts
  + research (volatile, after the breakpoint). **The footage manifest is a SCRIPT-path lever ONLY —
  never the description path** (the guard trips on `manifest`/filenames; feeding it into a description
  prompt invites a guarded-surface leak). Verify caching by storing `usage.cache_read_input_tokens` in
  ledger metadata (zero across repeated same-channel calls ⇒ a silent invalidator).
- **Sync** (`complete`): interactive description regen + tags — the path Banks judges. **Batch** (50%
  off): non-urgent narration scripts + backlog rewrites. Dispatch is chosen by the **job runner** (not
  the writer) via the `LLMRequest.batch` flag; batch settlement is a separate poll/reconcile CLI, kept
  **out of the interactive path**.

## Honesty constraints (unchanged from Layer 1)
- Research is **web/trend only** until YouTube read-scope exists; `youtube_signal_research` stays a
  `CapabilityUnavailable` **raising stub** — never empty-data-as-fact. `UnavailableResearch` reports
  web `available=False`; the writer is instructed to **work from niche knowledge and say so** in
  `research_notes`, never claiming it researched trends it didn't. **Do not expand OAuth.**
- **LLM provider ≠ research provider** — two separate §4.4 interfaces; don't fold web-search into the
  LLM provider (couples two swap axes).

## Provenance for Layer-2 tuning
Stamp every generated version: `repo.metadata.create_version(..., source="research_writer",
research_notes={style_spec_version, prompt_version, model, exemplar_set, tells_thresholds_version,
research_available, gen_params})`. Same stamp on `Script.provenance`. Version the constants
(`STYLE_SPEC_VERSION`, banned-tics version, tells-thresholds version). Gives the Layer-2 performance
loop versioned inputs to correlate voice/prompt revisions against CTR/retention — no Layer-2 code now.

## Doctrine doc
Add `house-voice-standard.md` at repo root — the *philosophy* (positive register; "calibrate tics to
the exemplar, never ban the voice"; the banned-tics rationale). Code (`authoring/style.py`,
`tells.py`) stays the enforceable source of truth and cites the doc's §, exactly as `guard.py` cites
`public-facing-output-standard.md §3`.

## Files
**New:** `ytagent/providers/{__init__,base,anthropic_provider,pricing}.py`;
`ytagent/authoring/{__init__,style,tells,script}.py`; `ytagent/metadata/llm_writer.py`;
`scripts/prove_slice5.py`; `house-voice-standard.md`.
**Edited:** `ytagent/metadata/description.py` (chapters optional — only change to the seam);
`ytagent/config.py` (optional `anthropic_api_key` + `anthropic_configured` in `safe_summary`);
`ytagent/seed.py` (seed `llm_pricing`+`fx` into `platform_settings`; register `style_exemplars` in
`WILDLIFE_CONFIG` as data); `ytagent/repo/ledger.py` (`write_llm_cost` + batch reconcile);
`telegram_bot/requirements.txt` (`anthropic>=0.40` — the only new dep); `.env.example`
(`ANTHROPIC_API_KEY=`).

## Deliverables (map to Banks's four)
1. **Provider layer + scoped-key wiring** — `ytagent/providers/` + config/deps/`.env.example`; the
   key-creation step flagged as human-only.
2. **Style spec** — `authoring/style.py` (house voice) + `tells.py` (anti-AI-tell scanner) +
   `house-voice-standard.md`, channel-general, applied per-channel from config.
3. **Autonomous description generation to §15** — `LLMWriter`; the lion's description regenerated by
   the agent and shown **side-by-side against the locked `lion_reference.py`**, with guard verdict +
   tell-scanner numbers.
4. **Autonomous footage-led script generation** — `authoring/script.py`; demonstrated on a short test
   topic (default **emperor penguin — Antarctic winter**; opposite biome so it's provably the agent's
   own writing, same wildlife voice, abundant claim-safe footage — Banks may redirect the topic),
   printed in full with the facts-used block + tell-scanner numbers, to judge against the lion script.

## Verification
- **Unit — `FakeLLMProvider` (Protocol impl, canned text + synthetic usage, no network):** tier
  routing (description→QUALITY, tags→CHEAP); the writer's output feeds `assemble_description` and the
  **guard trips** when the fake returns an internal-artifact string (writer-output regression); a fixed
  usage + fixed pricing fixture ⇒ expected `amount_gbp` and a correct `cost_ledger` row (category
  `ai_generation`, `channel_id`, `idempotency_key`, USD/FX). Asserted against the real compose Postgres
  (`:5433`). **Zero spend.** Plus `scan_tells(lion-doc-01-narration.md).flagged == False`.
- **Live proof — `scripts/prove_slice5.py` (human-run CLI, gated behind the key):** (a) autonomous lion
  description vs locked reference side-by-side + guard-clean + tell numbers; (b) autonomous emperor-
  penguin short script (~2.5 min, ~4 beats, ~250–300 words) + facts-used + tell numbers. Writes the
  real `cost_ledger` row(s) and prints month-to-date. **Pennies** (Sonnet prose, Haiku tags). No
  YouTube calls, no publish, no VPS. Existing dry-run + Layer-1 verify stay green.

## Expensive-to-retrofit decisions (locked)
1. **Tier in the request; model-id inside the provider** (routing not at call sites).
2. **Idempotency scheme + estimate→reconcile contract** (`llm:{request_id}` / `batch:{id}:{custom_id}`,
   `ON CONFLICT DO UPDATE`) — get right now or double-count / can't reconcile batch.
3. **Pricing + FX as DATA in `platform_settings`**, not constants.
4. **Provider DB-free; billing on the async path via an injected `UsageSink`.**
5. **Cache prefix ordering** (global house-style → per-channel exemplar/brief → per-video volatile);
   **manifest only in the script path**.
6. **Writer authors chapter LABELS from real timestamps, never generates times** (honesty invariant);
   chapters optional for uncut videos.
7. **LLM provider and research provider stay separate §4.4 interfaces**; `youtube_signal_research`
   remains a raising stub; **no OAuth expansion**.

## Deliberately NOT in this slice
Budget-governor enforcement (§4.10); Opus usage; a real web/trend research provider (stays
`UnavailableResearch`); the footage-inventory binder (Slice 4); estimating chapter timestamps for
uncut videos; putting tells in `guard.py`; any interactive bot command that spends without the
approval gate (proof is a human-run CLI).

## Conventions / safety
Channel-general (voice from config; wildlife is data). Add only this slice's stack (`anthropic` only).
Secrets via `.env`, never printed/committed. Build/prove on the Mac; never touch the VPS or ocean
stream. Commit locally only (no push). Tag command blocks `[ON YOUR MAC]`; no `#` lines in shell
blocks; end chains with `&& echo "OK..." || echo "FAILED...".`

# PLAN — the NOW bundle (correctness + control), specced to file level

**Status: PLAN ONLY. No code until Banks approves.** Scope: the "NOW bundle" from the platform-completion
plan — a real health command, the §1 allowance fix, the ROADMAP true-up, a subject-terms *flag*, and the
doc notes. No audience needed, no film production run, no ElevenLabs spend, no plan upgrade.

## Build order (note 3 governs it)
1. **Health command FIRST, then RUN it.** Its first green run is what upgrades the "zero blocking
   defects" verdict from *read-clean* to *runs-clean*. **If any verify FAILS, that failure list is the
   real defect list and takes priority over the rest of the bundle** — stop, report, triage before continuing.
2. **§1 allowance fix** (highest value of the planned changes — `main` currently ships a wrong cadence number).
3. **ROADMAP true-up + subject-terms flag + docs** (small).
4. **Re-run health** (all green) → record the upgraded verdict.

---

## 1. Health command  *(build first)*

**New `scripts/health.py`** — one command answering "do the codes work":
- `_OFFLINE`: ordered list of the 13 no-live-key verifies, each tagged `needs_db`:
  pure (no DB): `verify_cost_estimate`, `verify_slice3`, `verify_curation`, `verify_allowance` (new),
  `verify_subject_terms` (new); DB-required (monkeypatched providers): `verify_slice1`, `verify_layer1`,
  `verify_scheduler`, `verify_slice4`, `verify_slice5`, `verify_e2e`, `verify_scheduler_run`,
  `verify_spend_gate`, `verify_produce_resume`, `verify_publish`.
- `_OPTIONAL`: `verify_vision_fixtures` — run **only if `ANTHROPIC_API_KEY` present** (pennies), else skip with a note.
- **Preflight:** connect to Postgres via `settings.dsn()` with a short timeout. If unreachable and any
  `needs_db`, print the fix (`docker compose up -d postgres`) and exit **3 (environment, NOT a code defect)** —
  kept distinct from a verify FAILING.
- Run each verify as a subprocess `python -m scripts.<name>` (isolation — each does its own
  `asyncio.run` + `sys.exit`), inheriting `POSTGRES_HOST/PORT`. Capture returncode + last non-empty stdout line.
- Output: a table `verify | PASS/FAIL | secs`, **failures listed first**, then `ALL PASSED` / `N FAILED`.
  Exit **0** all-pass, **1** any-fail, **3** env.
- No live spend (vision is the only paid call, opt-in + cheap).

**New root `requirements.txt`** — pinned from actual imports (psycopg[binary], python-telegram-bot,
httpx, python-dotenv, Pillow, google-api-python-client, google-auth[-oauthlib], anthropic). Underpins the
health command's reproducibility; CI (`.github/workflows`) is a **follow-up backlog note, not this bundle**.

**New `Makefile`** (thin ergonomics): `health` → `python -m scripts.health`; `migrate` →
`python -m scripts.<migrate entry>`. Optional; documented either way.

**Verification:** `python -m scripts.health` runs green (the meta-check). This is also the diagnostic per note 3.

---

## 2. §1 allowance fix  *(highest value of the planned work)*

Kill the hardcoded `_EL_ALLOWANCE_CR = 53_599` that conflates recurring with rollover.

**`ytagent/config.py`:**
- Module constant (this comment is the ONLY thing carrying the uncertainty — note 1, must read as inference):
  ```python
  # INFERENCE from published ElevenLabs Starter pricing (~30,000 credits/mo). NOT API-sourced and NOT a
  # verified fact: the /v1/user/subscription endpoint returns character_limit = recurring base + rollover,
  # never the recurring base alone. UNVERIFIED until the 27 Aug 2026 reset (see BACKLOG). Do not present
  # this as sourced.
  _STARTER_RECURRING_ALLOWANCE_CR = 30_000
  ```
- `Settings.elevenlabs_recurring_allowance_cr: int = 30_000`; `load_settings` reads
  `ELEVENLABS_RECURRING_ALLOWANCE_CR` (default `_STARTER_RECURRING_ALLOWANCE_CR`); add to `safe_summary`.

**`scripts/roi_report.py`:**
- Delete `_EL_ALLOWANCE_CR`. Add a **pure** function (so it's testable without a live call):
  ```python
  def affordability(recurring_cr, available_now_cr, credits_per_film):
      # films/mo is computed off RECURRING (the sustainable number), never available_now
      sustainable_pm = recurring_cr / credits_per_film
      rollover_cr    = max(0, (available_now_cr or recurring_cr) - recurring_cr)
      return {"sustainable_films_pm": sustainable_pm, "recurring_cr": recurring_cr,
              "available_now_cr": available_now_cr, "rollover_cr": rollover_cr}
  ```
- In `run()`: read `available_now` LIVE via `get_tts_provider(settings).credit_status(key_cap=...)`
  → `account_limit`; on `None` degrade (report recurring only + "live read unavailable"). Headline
  cadence uses **recurring** (~4.4 films/mo, ~1/wk). Show both, and **flag `available_now > recurring`
  as one-off, non-recurring rollover**. Keep the incremental-cash framing (£0/film inside allowance).

**New `scripts/verify_allowance.py`** (offline, no DB, no keys — pure): asserts (a) `sustainable_films_pm`
uses recurring (30_000 / ~6_850 ≈ 4.4), (b) recurring and available_now stay **distinct** (rollover =
available_now − recurring, reported separately), (c) with available_now=None it degrades to recurring.
Added to `health.py` `_OFFLINE` (pure).

**`BACKLOG.md`:** dated **2026-08-27** — re-read `character_limit` after the reset; if 30,000, mark
`_STARTER_RECURRING_ALLOWANCE_CR` **verified** and update the comment (until then it is a labelled inference in code).

---

## 3. ROADMAP.md true-up  *(the omission)*

**`ROADMAP.md`:**
- §1.1 publish: `[ ] Publish — DEFERRED BY DESIGN…` → `[x] Publish — DONE. Both films live on
  @TheTalesofWildlifeandNature (yGdNuUB5f_I, EY9DhJdnt_w), 2 Aug 2026.`
- §1.3 Slices 1–6: `[ ]` → `[x]`. Platform-capabilities sub-list: mark scheduler (§14.5-adjacent B2) and
  the cost & ROI/ROAS governor (B3) `[x]`; leave the genuinely-unbuilt ones `[ ]`. Adjust the "IN
  PROGRESS" header to reflect the pipeline + B2 + B3 are done, the rest pending.

---

## 4. Subject-terms validator — FLAG (not reject)

**Decision (stated):** FLAG. Polysemy is search *quality*, not correctness; the lion run proceeded on a
bare term and produced a usable film; the 6c redesign removed pre-check gates so **sourcing decides**. A
hard reject would reinstate the removed gate and could block a viable subject. So: warn + log, never block.

**New `ytagent/scheduler/subject_terms.py`:**
```python
def flag_if_ambiguous(term: str) -> dict | None:
    # PURE heuristic, no LLM (no per-commission spend): a bare single word that is a known homonym /
    # captivity-prone animal name. Returns {"term","reason","suggestion"} or None. Suggestion from a small
    # static map (e.g. "lion" -> "African lion savanna"); None if unknown. NEVER blocks.
```
Heuristic: single-token term ∈ a small curated homonym/bare-name set (lion, seal, crane, jaguar, puma,
kite, …) → flag. Multi-word / qualified terms ("African lion savanna") → no flag.

**`ytagent/scheduler/runner.py` `_commission`:** after `next_subject`, call `flag_if_ambiguous`; if
flagged, `record_event("subject_term_flagged", …)` and continue — **commissioning is unchanged**.

**New `scripts/verify_subject_terms.py`** (offline pure): "lion" → flag with suggestion; "African lion
savanna" → None; assert flagging returns advisory data only. Add to `health.py` `_OFFLINE` (pure).
Plus one line in `verify_scheduler_run.py`: a flagged subject **still commissions** (non-blocking proven).

---

## 5. Docs

- **`CLAUDE.md`:** add the standing discipline — *"Claude (the reviewer) does not dictate direction;
  Claude Code is the engineer and plans the approach; Banks approves; Claude reviews."* (brief §0).
- **`BACKLOG.md`:**
  - **MLA (§8):** change to **deferred, trigger: any ElevenLabs plan change** (not "drop"). Record the
    language-axis finding: the *metadata* language axis is ALREADY reserved (`video_metadata.language`,
    `videos.primary_language`, language-keyed repo fns); the *audio-track* axis is **deferred, not
    reserved** — reason: needs a per-language narration path that multiplies TTS, and YouTube MLA
    audio-track upload isn't a settled Data-API call (Studio-era), so a stub would be speculative modelling.
  - **Social cross-posting (§14.7):** corrected reason — **gated on Shorts** (value is vertical
    short-form), not integration size. **Revisit WITH Shorts**, which is the same trigger.
  - The 2026-08-27 allowance-verify item (from §2).

---

## Verification for the whole bundle (no live spend, no production run)
- `python -m scripts.health` green — the meta-check; its first run is the real finding (note 3).
- New `verify_allowance` + `verify_subject_terms` green and wired into `health.py`.
- ROADMAP/CLAUDE/BACKLOG are doc edits (no code path).

## Files touched
**New:** `scripts/health.py`, `scripts/verify_allowance.py`, `scripts/verify_subject_terms.py`,
`ytagent/scheduler/subject_terms.py`, `requirements.txt`, `Makefile`.
**Edited:** `ytagent/config.py`, `scripts/roi_report.py`, `ytagent/scheduler/runner.py`,
`scripts/verify_scheduler_run.py`, `ROADMAP.md`, `CLAUDE.md`, `BACKLOG.md`.

## Estimate (×3): ~1 session
Health command is the bulk (~half); §1 + ROADMAP + subject-terms + docs ride alongside. May spill to
~1.5 if the health command's first run surfaces failures that must be triaged first (note 3), which is a
feature of the plan, not slippage.

## Explicitly NOT in this bundle
CI wiring (.github) — follow-up once the health command exists. Any marketing-arc component. Anything
needing an audience, analytics, a plan upgrade, or a production run.

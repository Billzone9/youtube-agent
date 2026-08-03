# YouTube Agent — Backlog

Deferred items, polish, and upgrade ideas. Nothing here blocks current work; we pull from it
deliberately. Add freely as ideas arise.

**Review cadence:** fortnightly.
**Next review:** 2026-07-08.
**Reminder mechanism:**
1. Claude checks the "Next review" date whenever we work and flags it if due (pull-based).
2. TODO (see below): a small server cron that pings Telegram every fortnight — a real
   time-based nudge using the bot we already run. Until that exists, the date field is the cue.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done (move done items to the bottom)

---

## Platform-completion deferrals & dated items (2026-08-04)
- `[ ]` **DATED — 2026-08-27: verify the ElevenLabs recurring-allowance constant.** After the billing
  cycle resets, re-read `character_limit` via `credit_status()`. If it returns ~30,000, the recurring
  base is confirmed — mark `config._STARTER_RECURRING_ALLOWANCE_CR` **verified** and update its comment
  (it is currently a labelled INFERENCE, not a sourced fact). If it returns higher, rollover was smaller
  than assumed and the sustainable-cadence number (~4.4 films/mo) must be re-derived. Until then the ROI
  report's cadence rests on an unverified inference — the comment is the only thing carrying that.
- `[ ]` **MLA multilingual dubbing (§8) — DEFERRED, trigger: ANY ElevenLabs plan change.** Not dropped:
  the blocker (up to 6× TTS spend on a Starter allowance that can't overage, no production runs) is a
  Banks-temporary constraint. **Language-axis reservation finding:** the *metadata* language axis is
  ALREADY reserved (`video_metadata.language`, `videos.primary_language`, language-keyed repo fns), so
  that half is free. The *audio-track* axis is **deferred, not reserved** — it needs a per-language
  narration path (multiplies TTS) and YouTube's MLA audio-track upload isn't a settled Data-API call
  (Studio-era), so a schema stub would be speculative. Reserve the audio-track axis only when the MLA
  upload mechanism is confirmed available programmatically.
- `[~]` **Native Shorts — ACTIVE (arc slice M1), was deferred.** The A′ marketing arc (2026-08-04,
  `PLAN_MARKETING_ARC.md`) makes credit-light Shorts the discovery centrepiece. Un-deferred: the old
  "no-production-runs" block is about full ~6,850-credit FILMS; a credit-light Short is ~0–640 credits
  (footage free + reused/light ambient bed + little/no TTS) and fits the current 5,684-credit window
  ~9–11×, so it is executable NOW. Assembly 9:16 is already first-class; the build is Shorts
  scripting/format + a Shorts density rule + the playbook format-mix + the Short publish path.
- `[~]` **Social cross-posting (§14.7) — UNBLOCKED (arc slice M3), was "deferred, gated on Shorts".**
  Its dependency (Shorts must exist) is satisfied by M1. No longer indefinitely deferred; sequenced
  AFTER YouTube Shorts prove out (YouTube Shorts need no external integration; TikTok/Reels/FB each do).
  Per-channel opt-in; YouTube stays primary. See `PLAN_MARKETING_ARC.md`.

## Marketing arc — carry-forward (small entries, fold into the arc plan; 2026-08-04)
- `[ ]` **Bed-manifest origin should be DERIVABLE, not asserted.** `beds-manifest.json` binds each bed's
  `elevenlabs_generated` attestation to its sha256, which is sound against accidental contamination — but
  the attestation is hand-written: no `request_id`, no `cost_ledger` row, no generation timestamp ties an
  entry to the ElevenLabs call that made it. That's weaker than the lion provenance rule (DERIVABLE source,
  not asserted). When a bed is generated THROUGH THE MACHINE (not lifted from an old production), bind its
  manifest entry to the ElevenLabs `request_id` + the `cost_ledger` row so origin is traceable rather than
  claimed. Not urgent at one operator; matters at channel #2 or if bed generation is automated.
- `[ ]` **Plan cadence against ~4.4 films/month, NOT 2/week.** The ROI report shows sustainable cadence
  ≈ 4.4/mo (~1/wk) on the recurring 30k allowance; the seed default is already `per_week: 1`. The live
  wildlife playbook carried a stale `per_week: 2` (leftover from the elephant supervised runs) — reset
  to `per_week: 1` on 2026-08-04 to match. The arc must design growth around ~1 film/week until a plan
  change lifts the ceiling; rollover can fund a short burst, not the cadence.
- `[ ]` **`scheduler/subject_terms.py:_AMBIGUOUS` is a hardcoded WILDLIFE word set in a channel-GENERAL
  engine** — the same anti-pattern as the vision gate's hardcoded canid definitions that had to be fixed
  before subject #2. It works for the wildlife channel but a second channel (e.g. financial news) gets
  no coverage and possibly false flags. Before onboarding a 2nd channel: make the ambiguous-term set
  per-channel config (channel registry / onboarding interview), or derive it, rather than a wildlife
  literal in code. Logged now so it isn't a surprise on channel #2.

---

## Anthropic cost — Claude Max for scripts (log only, NOT a cost measure — 2026-08-04)
- `[ ]` **Move script/description LLM to a Claude Max subscription instead of API — tidiness, not savings.**
  Be honest about the size: the TEXT LLM is not the cost centre. Scripts+description are ~£0.008/film
  (job 155), and the whole per-film LLM saving from Max is roughly **3p/film**. The real Anthropic driver
  is VISION (~£0.72/film, the sourcing gate — see next item), and **a Max subscription CANNOT serve API
  vision calls** (it's for interactive/subscription use, not programmatic image analysis). So Max saves
  the pennies and leaves the pounds untouched. Worth doing later for account tidiness; do NOT log it as a
  cost measure or expect it to move the ROI.

## Vision spend is the real Anthropic driver — reduce it (log options + est savings, DECIDE later)
- `[ ]` **The sourcing vision gate (~£0.72/film) dwarfs all other Anthropic spend; early-stop + verdict
  cache are built but the elephant run still verified far more candidates than the film needed** (42
  verified, 29 cache-hits, for a film needing ~27 clear). Concrete levers, with rough savings for Banks
  to decide between (NOT built — numbers only; all estimates off the ~£0.72/film vision anchor):
  1. **Tighter early-stop multiple** (currently 1.5× Σn_target). Drop to ~1.2× → stop verifying sooner on
     high-yield subjects. Est **~15–20% (~£0.11–0.14/film)**. Lowest risk (pure threshold; no accuracy loss
     on the clips that DO get used). Downside: a slightly thinner reserve pool.
  2. **Metadata pre-filter before ANY vision call** — drop candidates by title/tags negative keywords
     ("zoo", "captive", "statue", wrong species) before spending a frame. Biggest lever: **~30–40%
     (~£0.22–0.29/film)** if it removes a third of the pool pre-vision. Risk: metadata is unreliable (the
     reason we vision-check at all), so keep it to OBVIOUS negatives — conservative filtering only.
  3. **2 frames instead of 3** per candidate (currently majority-of-3). **~33% (~£0.24/film)** — but it
     removes the majority tiebreak the vision-gate-standard was calibrated on; needs recalibration on the
     3-frame fixtures before trusting it. Medium risk to gate accuracy.
  4. **Batch + prompt-cache** — cache the (large, fixed) vision system prompt across candidates and/or
     send multiple frames per request. **~10–20%** on input tokens, near-zero accuracy risk; more
     engineering than (1). Composes with the others.
  Options 1+2 together (~£0.35/film, low risk) look like the sweet spot, but Banks decides. Measure the
  actual per-call vision cost first to firm up these estimates before building any of them.

## B3 governor — the music balance reconciler (deferred; blocked on cap/quiet-window — 2026-08-04)
- `[ ]` **Settle ElevenLabs MUSIC per-call estimates against the truth.** TTS is now SETTLED (job 155:
  4,379 est vs 4,378 settled, 1.00x, all 18 rows by request_id via `reconcile_tts.py`). MUSIC remains
  `reconciled=false` (no per-call history exists for it), so its rate is still the ~12.5 cr/s from ONE
  hand-seeded lion row. Settle it via the guarded balance-delta (playbook disabled + assert no in-flight
  jobs + bound the delta to outstanding estimates), which also needs the near-exhausted key's cap raised
  to run a clean calibrated generation. The estimator is validated for TTS; this closes music.
  Balance-delta guards (fragile — the subscription `character_count` moves on every TTS+music call, and a
  scheduler can contaminate the window): run with the playbook DISABLED + assert no `producing`/in-flight
  jobs; bound the delta to the outstanding estimates ± tolerance and ABORT (don't mis-attribute) if it
  exceeds that. (`GET /v1/history` — the source that settled TTS — has no music equivalent, so music can
  only be settled this way.)
  - Currently ALSO blocked by the near-exhausted key (684 credits) — can't run a fresh calibrated music
    generation to measure credits/sec until the cap is raised. Build the guarded reconciler then.

## Two minor items from the job-276 resume (log now, fix later — 2026-08-03)
- `[ ]` **Music placeholder path when TTS resumes from cache.** When TTS reloads voiced beats from disk
  on resume (per-beat idempotency), the design/music stage's reference to the narration can fall back to
  a placeholder path rather than the reloaded mp3 in some resume orderings. Harmless in the runs seen but
  worth tightening so the design stage always binds the reloaded narration, never a placeholder.
- `[ ]` **Description regenerates (LLM spend) on every resume.** The metadata description is re-authored
  each resume instead of being checkpointed like the money stages, so a resumed job pays LLM tokens
  again for the same description. Checkpoint the authored description in `production_state` and reload it
  on resume (mirror the TTS/music idempotency). Small spend, but it's the same class of leak B3 is
  closing — fold into B3 or just after.

## KEY CAP HIT mid-production — the spend control worked; card BLOCKED on a human cap raise (2026-08-03)
- `[~]` **The ElevenLabs key "Youtube Agent" has a hard 15,000-credit cap and is down to 686.** The
  supervised elephant run (job 276) got through script + source, voiced beats 1–2, then ElevenLabs
  returned `401 quota_exceeded`: *"exceeds your API key quota of 15000 — 686 remaining, 756 required."*
  This is the STRUCTURAL SPEND CONTROL doing exactly its job (CLAUDE.md: scoped keys with hard credit
  caps) — it stopped the machine mid-production. **To complete ANY production Banks must raise/reset the
  key's quota (human-only spend change).** This film needs ~4,364 TTS + ~2,475 music ≈ 6,800 credits;
  ~1,850 already spent on beats 1–2, so ~5,000 more are needed → raise the cap to ~20,000 (or reset it).
  Then `JOB=276 python -m scripts.resume_job` completes to the card (beats 1–2 reload free — per-beat
  idempotent now). **Both TTS and music draw the SAME capped key**, so the whole tail is gated on this.
- `[x]` **Fixed: the client mislabelled `quota_exceeded` as "lacks TTS scope" and discarded ElevenLabs'
  body** — the false diagnosis that sent me hunting a scope/rate problem. `elevenlabs.py` now parses the
  401 body and raises `TTSQuotaError` (new, subclass of `TTSScopeError`) with the real message on a cap
  hit, `TTSScopeError` with the real body otherwise.
- `[x]` **Fixed: no retry + wrong classification on TTS calls.** `produce._synthesize_beat` now retries
  genuine transients (429/5xx/network, and a non-quota 401 after a prior success) with backoff, but
  FAILS FAST on `TTSQuotaError` (a hard cap is not transient) and on a first-call scope failure.
- `[x]` **Fixed: per-beat TTS idempotency.** A partial-resume re-charged already-voiced beats (the
  stage-level reload only fired when ALL beats existed). `_tts_all_beats` now reloads any beat whose mp3
  is already on disk — no re-charge.
- `[x]` **Fixed: the runner's `blocked` path persisted no reason.** It only alerted Telegram, leaving
  `jobs.error` empty (which blinded the job-276 diagnosis). It now writes `str(e)` to `jobs.error`.
- `[x]` **Credit gate at 4→5 (Banks, 2026-08-03): check CREDITS, not just pounds.** The old gate cleared
  job 276 at £9.10 < £50 then ran out of credits mid-spend. `produce._credit_gate` now queries the
  ElevenLabs key's remaining credits (subscription `character_count` + a config'd per-key cap
  `ELEVENLABS_KEY_CREDIT_CAP`, since ElevenLabs exposes no per-key cap via GET) and compares against the
  credits STILL to spend (unvoiced beats + ungenerated music; done stages don't re-charge). If short →
  `SpendGatePause("credits")` BEFORE any spend, alert names needed vs available. Degrades (no block) if
  the provider can't report. Tested 3 ways; sits beside the per-job + rolling-ceiling gates.
- `[x]` **Provider-error doctrine + audit (Banks, 2026-08-03):** `provider-error-standard.md` — a client
  that raises MUST carry the upstream message through, never substitute a guess. Audited: ElevenLabs
  (fixed), Pexels/Pixabay/download (fixed — bare `raise_for_status()` dropped the body → now
  `httpx_error.raise_for_status_with_body`), YouTube `_http_error` (fixed — carried only `reason`, now
  carries Google's message + only ADDS the scope hint), Anthropic (OK — SDK carries the message).
- `[ ]` **Per-stage timings still partial:** script 2.0 min, source 5.8 min (WARM — 29 of 42 verified
  were cache hits; cold ≈ 30–40 min), TTS partial (2/6 beats), design/assemble/submit UNREACHED —
  blocked by the key cap until raised. A cap raise + resume yields the missing numbers.

## Phase 0 polish (non-blocking)
- `[ ]` Add more ocean clips to `~/youtube-agent/assets/clips/`, then rebuild for a longer loop
  (slim bitrate already baked into `build_master.sh`). Reduces visible repetition.
- `[ ]` On a future rebuild, optionally cap bitrate ~6800k to match YouTube's suggestion.
- `[ ]` Tidy the harmless duplicate Docker apt-source warning.
- `[ ]` Lengthen the master beyond the current 6-minute loop (overlaps with "add more clips").

## Infrastructure / friction
- `[ ]` Fix SSH key passphrase friction (macOS keychain integration) so connecting is seamless.
- `[ ]` Tidy old ended broadcasts from the YouTube Studio Content list.

## Process / tooling
- `[ ]` Build the backlog-review Telegram reminder cron (the time-based nudge described above).
- `[ ]` Store the project repo URL in Claude's memory once the repo exists, so Claude auto-knows
  where to read the roadmap/backlog/spec each session.
- `[ ]` Decide public vs private repo (recommendation: public, secrets gitignored — lets Claude
  read it directly; private means re-pasting files each session).

## Scheduler / playbook (Slice 6)
- `[ ]` **Footage availability must inform topic selection.** Before committing to a topic, the
  scheduler/playbook should PROBE library coverage — a cheap sourcing dry-run (search Pexels/Pixabay
  for the topic's core subject, count gate-eligible matches) — and avoid or re-shape topics the stock
  libraries can't dress. **Evidence (Slice 4 proof, 2026-07-18):** the emperor-penguin script sourced
  only **1/5 shot-briefs** — free Pexels/Pixabay have almost no emperor-penguin-in-Antarctic-winter
  footage, so 4/5 briefs failed loudly (correctly, not padded). Abundant subjects (lion, ocean,
  generic wildlife) have deep coverage; niche species/biomes may not. Topic choice should be
  coverage-aware, not just trend/interest-aware. (Also feeds the cost-gated generative-B-roll
  fallback decision for the rare must-have shot stock can't provide — spec §4.3.)

## Footage-coverage finding → PROMOTED to `footage-coverage-standard.md` (2026-08-03)
The "non-elephant megafauna are captive-polluted; elephant uniquely coverable" finding is no longer a
backlog item — it is a **standing structural constraint** on the whole channel, now written up in
`footage-coverage-standard.md` (three coverage classes + evidence table) and referenced from
`footage-feasibility-standard.md`. Only the still-actionable **code** residue stays here:
- `[ ]` **`scripts/vet_pool.py` needs a per-probe timeout before batch use** — it is slow (~8 min/sample-20
  probe) and one hanging candidate stalls the whole run (had to be killed near completion during vetting).
- `[ ]` **Discover more class-1 (deep + wild) subjects** — elephant is the only proven one. Candidates to
  vet: large-range wild fauna, birds in flight, marine life, aerial herds (see the doctrine in the standard).

## Contradiction detector false-fires on HOMONYM subject terms (log, do not chase — 2026-08-03)
- `[ ]` **The lion run's 23 "contradictions" were the sea-lion ambiguity, NOT a gate regression.** 19 were
  pinnipeds ("sea lion", "seal", "walrus"), 3 were "lion (sculpture)"; ALL were correctly `clear_mismatch`
  by the species gate. They flagged as contradictions only because `features_indicate` ("sea **lion**",
  "**lion** sculpture") contains the subject noun "lion" as a SUBSTRING, so `_indicates_subject` thought
  the features named the subject while the verdict rejected it. The detector's noun match is substring-
  based; a homonym subject term trips it. Fixed for real by DISAMBIGUATING the term (subject-terms-
  standard.md) — "African lion" surfaces no sea lions, so the contradictions vanish. If ever chased: make
  `_indicates_subject` word-boundary + homonym aware ("sea lion" ≠ "lion"). Low priority given the term fix.

## The real 6c constraint is FOOTAGE COVERAGE, not the gate → folded into the standard (2026-08-03)
Superseded: the "gate redesign works; blocker is footage coverage" finding (lion PROCEEDED past its
INFEASIBLE verdict → real source → 10 clear → SOURCING_SHORT, the redesign vindicated) is now captured in
`footage-coverage-standard.md`. The scheduler is CORRECT + SAFE (proceeds, records real yields, caps
consecutive sourcing failures at 3, then pauses + alerts). Advisory ordering (a mid-size probe to order
the pool most-likely-first, never a gate) was BUILT — see `scripts/vet_pool.py` + `subject-terms-standard.md`.

## BLOCKS unattended 6c — the commissioning VERDICT-GATE is unreliable (found in the supervised run)
- `[ ]` **The probe VERDICT is a poor commissioning gate; use the DISTRIBUTION, let sourcing be the gate.**
  The first supervised `tick()` (2026-08-02) exposed this on REAL probe data: of 7 subjects probed for the
  wildlife channel, only the elephant was FEASIBLE. **lion → INFEASIBLE (E=34, a DEEP pool)**, giraffe /
  zebra / wildebeest → INCONCLUSIVE-SHALLOW, penguin → INFEASIBLE, and **flamingo flipped MARGINAL →
  INFEASIBLE across two probes 15 min apart** (small-sample noise). With the verdict as the gate the
  scheduler `paused_pool` every time — it would not commission almost anything, i.e. not autonomous.
  The routing/classification is CORRECT (every subject was skipped per its verdict, no ask, paused +
  alerted) — the problem is the GATE, not the runner. Root cause is the diagnostic's known point: the
  probe's 10-sample yield does not predict the film-wide footage-led yield (elephant: probe ambiguous,
  yet 54 clear). **RECOMMENDED (design decision for Banks, NOT built):** stop gating commissioning on
  the probe verdict — keep the probe for the observed DISTRIBUTION (which drives footage-led scripting,
  and is reliable) and let `source_film`'s real yield be the feasibility gate: proceed to production,
  and if sourcing comes up short the runner ALREADY routes `ProductionError` → next subject (no spend
  lost — it fails before TTS). Early-stop + the verdict cache make a real source attempt cheaper. Until
  this is decided, the scheduler must not run unattended (it would just churn probes and pause).
- `[ ]` **Per-stage production timings still unmeasured** — no production ran (everything failed the
  gate), so probe/script/source/TTS/design/assemble wall-clock is still pending a subject that commissions.

## RESOLVED (6b-bis) — auto-scripts now footage-led; the block on 6c is cleared
- `[x]` **Fixed 2026-08-02.** ScriptWriter.write() now REQUIRES a probe-observed footage distribution
  (structural — no default, fails loud) and an unsourceable-content scanner (`authoring/sourceability.py`)
  regenerates archival/photo/illustration/CGI briefs in the bounded-retry loop. `_st_script` probes →
  distribution → writes, so the auto path cannot regress to script-first. PROOF (same failed subject,
  sourcing-only): **8 clear → 54 clear (PASS, all 7 beats)** — see `DIAGNOSTIC_SOURCING_YIELD.md`. 6c is
  unblocked. (Original analysis retained below for the record.)

## BLOCKS 6c — auto-scripts source poorly because briefs are written script-first, not footage-led
- `[ ]` **Root cause found (see `DIAGNOSTIC_SOURCING_YIELD.md`).** Same subject `african elephant`
  yielded 52 clear clips when its script was written to a probe's OBSERVED distribution (The Old Paths)
  vs 8 clear when the ScriptWriter wrote briefs FIRST (macros, trunk close-ups, communication, archival
  ivory-trade footage, ecological-impact shots the libraries lack). It is **(a) brief specificity →
  (b) query construction** — NOT rate-limiting (0 search errors) and NOT the no-repeat guard
  (`_source_all_beats` passes no `exclude_ids`; cached clips are reused; the 8 fresh-clear have zero
  overlap with the 26 — different queries, not exclusion). **Recommended fix: footage-led auto-scripting**
  — feed `probe_feasibility`'s observed season/habitat/time/shot distribution into the ScriptWriter (the
  doctrine the elephant proved, not wired into the auto path) + forbid unsourceable/archival content.
  This is a PREREQUISITE input to 6c's commissioning design, not optional polish. Diagnostic committed;
  no fix built pending Banks's decision.

## Probe vs film-wide yield disagree (found in the 6b real run, 2026-08-02 — log, do not chase)
- `[ ]` **The feasibility probe over-estimated giraffe.** `probe_feasibility('giraffe')` returned
  MARGINAL with E=17 and 9/10 both-match on its sample, but the full `source_film` run found only **5
  clear clips across 935 candidates** (2 gate-rejected) — a ~0.5% film-wide yield, far below the probe's
  90% sample. The refactored pipeline failed loud correctly (before any TTS spend), so no harm — but the
  probe's small-sample yield is not predictive of the deep film-wide yield. When the scheduler (6c) uses
  the probe to gate commissioning, treat MARGINAL as "verify with a fuller probe" — or align the probe's
  query construction (must_terms/wild strictness) with `source_film`'s, since they currently disagree.
  Cheetah similarly probed INCONCLUSIVE-SHALLOW (E=1). Elephant/lion have genuinely deep coverage.

## SECURITY — the YouTube token permits FAR more than the agent uses (publish slice, 2026-08-02)
- `[ ]` **`youtube.force-ssl` is broad; the restriction is our CODE SURFACE + the Telegram gate, NOT the
  scope.** There is NO "only videos this app uploaded" OAuth scope — force-ssl (needed for videos.update
  → set metadata + flip public) also grants **delete videos, manage playlists, post/moderate comments,
  edit captions, and change channel branding**. The agent never does any of those because *no code path
  exists* for them, and publishing is Telegram-gated. **REVIEW RULE:** any future code that touches the
  YouTube client (`ytagent/youtube.py`) must be reviewed against this — the token will happily perform
  far more than the agent should ever do. Keep `youtube.py` the single write surface: `publish` (insert,
  private-locked) + `update_public` (own-DB-ids only, channel-asserted). Do not add delete/list/playlist/
  comment/branding calls without an explicit, gated, reviewed reason. Consider (later) a periodic audit
  that lists what the token *could* do vs what our code *does*, so drift is visible.
  - **REVIEW (2026-08-04) — the cohort playlist grows the surface; approved with confinement.** M1's
    Shorts success-measurement needs a YouTube-side cohort marker (an UNLISTED cohort playlist,
    reconstructable via `playlistItems.list`) so cohorts survive without the DB (PLAN_M1_SHORTS note 2).
    That means `youtube.py` gains `playlists.insert` (create the ONE cohort playlist once) +
    `playlistItems.insert` (add a cohort Short). force-ssl already permits both — **no new scope**; the
    growth is the CODE SURFACE, which is why this review is on the record. **Confinement (mirror
    `update_public`):** `playlistItems.insert` adds ONLY our own uploaded `youtube_video_id`s (the
    own-DB-ids set) to ONLY our cohort playlist (id stored in our config/DB); `playlists.insert` creates
    ONE unlisted playlist, recorded. NO delete, NO listing/adding to arbitrary/others' playlists, NO
    comment/branding. The add runs as part of the already-Telegram-gated publish. Reason the surface
    grew: cohort evidence must survive on YouTube, not only the DB — an explicit, reviewed, gated reason.
- `[ ]` **Elephant #61 metadata bookkeeping (minor, not blocking).** EY9DhJdnt_w's LIVE description is
  guard-CLEAN (verified — Amendment B), but its `video_metadata` row shows `applied_at=NULL` though the
  text is live (set at upload). A cosmetic bookkeeping gap in the mark-applied path for that older
  upload; the live text is correct. Reconcile when the elephant is next considered for public (out of
  scope for the lion-only publish slice).

## Audio-design slice — deferred polish (from the elephant end-to-end run, 2026-08-01)
- `[ ]` **SFX (sound-generation) scope is BLOCKED** — the ElevenLabs key 401s on `/v1/sound-generation`
  ("key lacks the sfx scope"). Pre-flighted live; the film shipped WITHOUT SFX (graceful degradation,
  as designed). To enable a scene-earned SFX (e.g. a low infrasound rumble under beat6 "what passes
  below hearing"), Banks adds the sound-generation scope (or a scoped key) in the ElevenLabs dashboard
  — a human-only spend-capability change. Then pass an `SfxSpec` to the conductor.
- `[ ]` **SFX placement needs the measured timeline.** `Sfx.at_s` is an ABSOLUTE master offset, but the
  timeline is only known after TTS + breathers. To place an SFX inside a specific beat, compute that
  beat's absolute start from the measured narration lengths + breathers + cold-open + xfade overlaps
  AFTER TTS, then set `at_s`. Deferred with the scope block above.
- `[ ]` **Music cue `kind` mislabel (cosmetic).** `music/elevenlabs.py:generate` infers `kind="bed"`
  when the prompt contains "bed"/"ambience" — the `theme` cue's prompt says "a bed of feeling", so its
  ledger row reads "bed cue 'theme'". The cue file + per-beat assignment are correct; only the ledger
  `kind` label is off. Pass `kind` explicitly from the conductor instead of sniffing the prompt.
- `[ ]` **Hard music-loop seam under long beats.** A compact cue (35–45s) is `stream_loop`ed to cover a
  62–72s beat (the lion recipe), so there is a hard-cut loop point mid-beat. Inaudible-ish under
  narration at −16 dB, but a per-beat `acrossfade` self-loop (like the bed) would remove it. Deferred —
  this matches the approved lion recipe; revisit only if a beat's seam is audible on review.
- `[ ]` **Master is 736 MB for 6.2 min** (CRF 18, 1080p). Fine for a private master; consider a
  delivery-encode pass (CRF 20–22 / two-pass) before any real upload if size matters.

## Known defect (log, do not chase)
- `[x]` **Contradiction detector — false-fire — FIXED 2026-08-01.** The false-fire came from the
  `names_other` branch (`features_indicate` names something other than the subject, yet species
  accepts → flagged). When the film subject wasn't propagated into `Expect.subject` (scene-only briefs
  set it to 'herd'/'savanna'), the gate's correct `features_indicate="African elephant"` vs an
  `expect.subject` of 'herd' tripped it on every accepted clip (3–4/run). Dropped the branch:
  `contradiction = _indicates_subject(features_indicate, subject_noun) and species == CLEAR_MISMATCH`
  only — the real "recites the subject then rejects it" signal. Regression `[4d]` in verify_curation;
  the re-run logged **0 false-fires** (2 legitimate contradictions remained, on the kept branch).

## Small robustness (from the elephant slice, 2026-08-01)
- `[ ]` **ScriptWriter JSON extraction is fragile.** `_extract_json` failed on one elephant generation
  (unescaped char in a long VO → JSONDecodeError propagated; the retry loop only re-runs on AI-tell /
  pacing / runtime, not on a parse error). A re-run succeeded. Fix: catch the parse error inside the
  bounded retry loop (re-prompt "return STRICT valid JSON"), and/or a light JSON repair pass.

## Feasibility search reach (from the elephant slice, 2026-08-01)
- `[x]` **Search reach + structural depletion — FIXED 2026-08-01 (film-wide sourcing + allocation).**
  Root cause of the elephant Stage-1 short (beats 3–7 returned 0 verified, surfacing muskox/woolly
  sheep): scene-only briefs never name the animal, so `build_query_plan` extracted scene words
  ('herd'/'savanna') into `must_terms` — an off-subject clip tagged 'herd' passed the rank filter, and
  real elephants were never reached. Fixes: (1) `build_query_plan(subject=…)` FORCES the film subject
  into `must_terms` AND every query (`_enforce_subject`); (2) NEW `source_film()` gathers ONE film-wide
  verified pool (union of all beats' subject-anchored queries) then ALLOCATES to beats by fit — no
  earlier beat starves a later one (fixes the structural depletion); (3) real pagination (`page` on the
  providers + `_search_all`, `per_page=50`, `pages=2`). Wired into BOTH Stage-1 curation and the render
  path (`_source_all_beats`). Re-run: **all 7 beats PASS** — pool 1731 candidates → 157 eligible → 90
  verified → 52 clear + 6 reserve (32 gate-rejected incl. a lion and captive elephants) → 26 allocated.
  The muskox/sheep are gone (they now score 0.0). Regression `[6]` in verify_curation.

## Small robustness (from the film-wide elephant re-run, 2026-08-01)
- `[ ]` **One vision verdict came back unparseable/malformed** (pexels 35023064) — handled safely
  (defaulted to species+wild `clear_mismatch` → rejected, 1 of 90), but a malformed-JSON RETRY inside
  `vision_check` (as ScriptWriter now does) would recover the clip instead of discarding it.
- `[ ]` **`source_film` verify pass is slow** — `max_verify=90` × 3 Haiku frames each + downloads ran
  ~45 min wall-clock (network/API latency, not CPU). The pool was plenty deep by ~40 clips. Tune:
  early-stop once the clear pool comfortably exceeds Σ n_target (e.g. 1.5×), and/or cache vision
  verdicts by asset_id so re-runs don't re-pay. Not blocking; the run completed and all beats passed.

## Known defect — species discrimination WITHIN a family is unproven (from the feasibility slice, 2026-08)
- `[ ]` **BLOCKER before any look-alike subject (leopard/cheetah, small cats, most raptors).** Removing
  the morphology definitions fixed over-strictness, but the definition-free gate now reads the old coyote
  clip (142472) as a grey wolf, and the live calibration only tests CROSS-family discrimination (a lion
  is not a wolf — trivially easy). Within-family discrimination (wolf vs coyote, leopard vs cheetah) is
  therefore UNPROVEN. Elephants/giraffes/zebra have no look-alikes, so this does NOT block film #2 — but
  it must be solved (per-subject confusable list handed as DATA? a two-stage "is it X or the look-alike Y"
  prompt?) before any subject that shares a silhouette. Feasibility should also flag "look-alike risk" per
  subject so the playbook avoids these until it's solved.

## Vision gate — hardening (PROMOTED into the feasibility slice, 2026-07-31 — no longer deferred)
The two items below are now IN the feasibility slice (changing subject requires a channel-general gate):
- `[ ]` **VISION GATE IS NOT CHANNEL-GENERAL — fix before the SECOND subject (BLOCKER for subject #2).**
  `ytagent/sourcing/vision.py` hardcodes grey-wolf/coyote morphology in `_PROMPT_DEFINITIONS` **and** in
  the `_SYSTEM` prompt's examples. On an elephant or eagle film the gate is primed with canid examples,
  and `definition_echo` compares features against irrelevant (wolf/coyote) definitions → meaningless
  numbers. Violates "general platform, not a niche tool — channel-general from slice 1" (CLAUDE.md /
  ROADMAP). Fix: species definitions become **per-subject DATA derived from the brief** (the expected
  subject + its confusable look-alikes), not constants in code/prompt. Wildlife-general, not wolf-specific.
- `[ ]` **Consider REMOVING species definitions from the prompt entirely (candidate real fix for
  definition-echo).** The model can only RECITE because we handed it the script. If `_SYSTEM` asked it to
  describe what it SEES without supplying morphology definitions, there'd be no canned text to echo —
  possibly the real fix rather than measuring recitation after the fact. **Do not act yet:** the def-echo
  numbers on the ACCEPTED winners from the clean wolf Stage-1 run are the evidence for/against this;
  decide once that data is in.

## Phase 1 enablers (promote to ROADMAP when we start them)
- `[ ]` Build asset-provenance logging into the production pipeline (URL + contributor + license
  + timestamp per clip). Required by the footage-recon findings.
- `[ ]` Choose the ElevenLabs narration voice: a specific generic deep British male (NOT a clone
  of any real narrator). Set a per-video narration budget.
- `[ ]` Decide MLA launch languages — data-driven, start with 1–2 that the audience data justifies,
  not all at once (cost scales per language).
- `[ ]` Pick the grounded-research source for script fact-checking (spec names e.g. Gemini).

---

## Done
(empty — move completed items here with the date)

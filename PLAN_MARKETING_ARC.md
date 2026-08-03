# PLAN — Marketing / audience arc (A′: credit-light Shorts as the discovery engine)

**Status: PLAN. No build until Banks approves a slice.** Approved posture: **A′** — grow via credit-light
vertical Shorts (the discovery lever at 0 subs), with ~1 long-form/week banking watch-hours toward the
4,000-hour AdSense gate. Cadence is planned against the sustainable **~4.4 long-form/month (~1/week)**;
Shorts are near-free in credits so they do NOT compete with the long-form allowance.

## The gating fact (resolved, verified live 2026-08-04) — A′ is provable NOW
- **Spendable credits: 5,684** (key cap verified 20,000; used 14,316; resets 27 Aug). `.env` sets the cap
  to 20,000 so the credit gate reads 5,684 correctly (the `config.py` fallback default still says 15,000
  — harmless but should be trued to 20,000).
- **One credit-light Short costs ~0–640 credits:** footage 0 (stock); ambient bed **0 if it reuses an
  existing clean own/synthetic bed**, or ~520 for a fresh 30s bed (30s × 15 cr/s × 1.15 retake headroom);
  TTS 0 (no voice) or ~120 for a one-line hook.
- **Fits the 5,684 window ~9–11× at the generated end, effectively unlimited at the reused-bed end.**
  So the Shorts proof is executable TODAY — it does NOT need to wait for the 27 Aug reset. (A full
  ~6,850-credit LONG-FORM still can't run before the reset; that constraint is unchanged and is why the
  arc proves discovery on Shorts, not on another film.)

## Backlog reconciliation (resolved here so plan and backlog agree — item 1)
A′ makes Shorts the centrepiece, which changes two backlog entries written yesterday:
- **Native Shorts: DEFERRED → ACTIVE (this arc, slice M1).** The deferral cited "production + spend under
  the no-runs constraint." That constraint is about full ~6,850-credit FILMS; a credit-light Short is
  ~0–640 credits and fits the current window many times over, so it is executable now. Un-deferred.
- **Social cross-posting (§14.7): "deferred, gated on Shorts" → UNBLOCKED, slice M3.** Its stated
  dependency (Shorts must exist) is met by M1. It is no longer indefinitely deferred; it is sequenced
  AFTER YouTube Shorts prove out (YouTube Shorts need no external integration; TikTok/Reels/FB do).
(Both BACKLOG entries are edited to match this in the same change.)

## The arc, sequenced

### M1 — Credit-light Shorts pipeline + YouTube Shorts publish  *(the centrepiece; executable now)*
- **Format:** 9:16 (assembly already first-class), ~15–40s, footage-led (one striking clip or a 2–3 clip
  micro-sequence), **reused/light ambient bed** (prefer a clean existing bed → 0 credits), optional
  one-line hook (text overlay or ~120-char TTS). `#Shorts`.
- **Reuse the pipeline:** EditSpec 9:16 target + `for_format`; a Shorts-scaled density rule (few clips,
  short); the noise gates and public-facing-output guard apply unchanged.
- **Publish:** a YouTube Short is a <60s 9:16 upload with `#Shorts` — the existing `YouTubePublisher`
  path handles it; human-gated as always; AI-disclosure line still applies.
- **Playbook (§14.4 format mix):** add a Shorts cadence to the wildlife playbook (e.g. 3–4 Shorts/week
  alongside ~1 long-form/week). Format mix is per-channel config.
- **Proof (no film run needed):** produce 1–2 credit-light Shorts through the machine to the Telegram
  card — ~520 credits each if a fresh bed, ~0 if reused. Within the 5,684 window.
- **Prerequisite:** true the `config.py` key-cap fallback to 20,000 (one line) so the gate math is right
  even without the `.env` override.

### M2 — Competitor & trend analysis (§14.5)  *(research; no audience needed; runs alongside M1)*
Feeds WHAT Shorts/topics to make and surfaces content gaps. Grounded research (the swappable provider
layer), no spend of consequence, no analytics dependency. Can proceed in parallel with M1.

### M3 — Social cross-posting (§14.7)  *(unblocked by M1; per-channel opt-in; after YouTube Shorts prove out)*
Cross-post the proven Shorts to TikTok / Instagram Reels / Facebook — the platforms whose payload is
vertical short-form. Per-channel opt-in (wildlife is the test tenant); YouTube stays primary. Sequenced
after M1 has a working Short + early signal, because each external platform is its own auth/ToS/rate-limit
integration and shouldn't be built before there's a Short worth posting.

### Deferred within the arc (needs public data / a new scope)
- **Metadata performance loop (Layer 2, §15) + B4 learning:** needs YouTube Analytics — a **new OAuth
  scope with a security review attached** (the `youtube.force-ssl` breadth rule) — and real public data
  that won't exist until the Shorts/videos run. Deferred until M1 has produced measurable public signal.

## Tier B (higher cadence via a plan change) — recorded, NOT recommended
If Banks ever weighs lifting the ceiling: a one-tier ElevenLabs upgrade multiplies the recurring
allowance several-fold and would unlock narrated Shorts at volume + higher long-form cadence. **The
~£15–20/mo figure is UNVERIFIED — same class as the 30k recurring-allowance inference — and must be
labelled as such wherever recorded.** Not proposed here; A′ deliberately proves the discovery flywheel on
the £5/mo plan first, so the upgrade decision (Banks's alone) rests on real evidence, not assumption.

## Sequencing summary
M1 now (credit window open) ‖ M2 in parallel (research) → M3 after M1 shows a working Short → Layer-2/B4
when analytics is unlocked and public data exists. Each slice planned to file level before its code.

## Estimate (×3)
M1 ~1–2 sessions (reuses 9:16 assembly + publish; the new parts are Shorts scripting/format + the
playbook format-mix + a Shorts density rule). M2 ~1–2. M3 ~2–3 (per external platform is its own
integration). Layer-2/B4 deferred (data-gated). Honest near-term: **M1 next**, provable inside the
current 5,684 credits.

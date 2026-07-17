# Slice 5 — message for review

**Status:** everything non-live is built, verified zero-spend, and committed locally
(`f935d06`, branch `slice5-llm-writer`). The live proof (`scripts/prove_slice5.py`) is written but
**held** — it makes the first real (paid) Anthropic calls, and I'm waiting on your go.

---

## The question I'm waiting on

**May I run `scripts/prove_slice5.py`?** It makes the first real (paid) Anthropic API calls
(estimated a few pennies — see below). It runs on the Mac only: no YouTube, no publishing, no VPS,
no touching the ocean stream. It writes the real token spend to `cost_ledger` and prints
month-to-date.

Also: the script's autonomous-script demo uses the **emperor penguin (Antarctic winter)** as the
test subject. If you'd prefer a different subject, tell me and I'll swap it before running.

---

## Calibration numbers (already confirmed, zero spend)

The AI-tell scanner is calibrated so the **house voice is the reference**, not a target to flag.

Measured lion narration baseline (`lion-doc-01-narration.md`):
- **2.50 em-dashes per 100 words** (threshold to flag is 4.0/100w — the lion sits comfortably under it)
- **0 exclamation marks**
- 3 deliberate tricola — counted as **advisory only**, never gated

Result: `scan_tells(lion narration).flagged == False` ✅ — the scanner treats the lion voice as clean.

Sanity check (an obvious AI-tell paragraph: *"In this video we'll explore… not only… but also…
testament to nature's tapestry!"*) → `flagged == True` with the right reasons ✅.

### Full zero-spend verification (`scripts/verify_slice5.py`) — ALL PASSED
- **Tier routing** — description prose → Sonnet (QUALITY); tags → Haiku (CHEAP).
- **Guard regression** — an LLM-emitted `lion-doc-01-footage-manifest.md` in the opening is caught
  and refused by the existing guard (the anti-leak net still holds on generated text).
- **Lion tell-calibration** re-asserted (`flagged=False`).
- **Cost math** — fixed usage (100k in / 20k out on Sonnet) → **$0.60 → £0.47**, correct
  `ai_generation`/Anthropic ledger row, idempotent replay (no duplicate row), fake row cleaned up
  so no fake spend pollutes the honest baseline.
- **Regressions** — Slice 1 (`simulate_slice1`) and Layer 1 (`verify_layer1`) both still green.

---

## Cost estimate for the live run (`prove_slice5.py`)

Computed locally from the exact rendered prompts against the seeded prices — **no API call made yet**:

| Call | Model | ~input tokens | ~output tokens |
|---|---|---|---|
| Lion description prose | Sonnet | 1,190 | 380 |
| Lion tags | Haiku | 1,060 | 160 |
| Lion chapter labels | Haiku | 1,030 | 130 |
| Penguin script | Sonnet | 2,770 | 850 |

- **Expected: ~$0.034 ≈ £0.027** (about 3 pence).
- **Worst case** (both Sonnet calls hit the max 2 AI-tell retries): **~£0.05**.
- First run has no cache hits yet; still a few pennies against the £200 month-1 ceiling.

---

## What the live run will produce for you to judge

1. **The agent's own lion description**, printed side-by-side against the locked hand-authored
   reference (`ytagent/metadata/lion_reference.py`) — same subject, so you can see whether its
   *unaided* prose lands the register, plus the guard verdict and the AI-tell numbers. It also stores
   the result as an authored `video_metadata` version (`source='research_writer'`, **not** applied —
   truthful, not live).
2. **A full autonomous script on the emperor penguin** (a subject with no lion vocabulary to
   recycle — proof it's the agent's own writing), with the facts-used/accuracy block and the AI-tell
   numbers, to judge against the lion script's voice.

The test that matters, in your words: you reading a description and a script the agent wrote *itself*
and judging whether they hit the house voice with no AI tells.

---

## What was built in this slice (all committed at `f935d06`)

- **`ytagent/providers/`** — the swappable LLM interface (spec §4.4): `base.py` (pure types —
  `ModelTier`, `CacheableBlock`, `LLMRequest`, `TokenUsage`, `LLMResponse`, `LLMProvider`/`UsageSink`
  protocols), `anthropic_provider.py` (the one concrete impl; tier→model-id routing lives here;
  prompt-cache markers; batch; lazy SDK import; DB-free — pushes token usage to an injected sink),
  `pricing.py` (four-bucket USD→GBP from `platform_settings`), `__init__.py` factory
  `get_llm_provider` (returns `None` with no key → honest degradation to `NullWriter`).
- **`ytagent/authoring/`** — `style.py` (channel-general house voice + banned-tics, `compose_style` →
  `StyleSpec` cacheable prefix; the lion voice enters only as config + exemplar data),
  `tells.py` (the AI-tell scanner — FLAGS, never mutates; calibrated to the lion baseline),
  `script.py` (footage-led `Script` writer; `footage=None` path only — shot-briefs are an *output*,
  not a consumed input, so it doesn't reach into Slice 3/4). Plus `house-voice-standard.md` doctrine.
- **`ytagent/metadata/`** — `llm_writer.py` (`LLMWriter` fills the `Writer` seam: QUALITY prose +
  CHEAP tags/labels, tell-scan + regenerate, provenance stamp); `description.py` — `assemble_description`
  `chapters` now **optional** (never fabricate timestamps for an uncut video; the lion keeps its real
  chapters).
- **Cost / config** — `repo/ledger.py` `write_llm_cost` (idempotent on `llm:{request_id}`, USD/FX,
  no migration needed); `seed.py` seeds `llm_pricing`+`fx` and registers `style_exemplars` as data;
  `config.py` optional `anthropic_api_key` + `anthropic_configured` in `safe_summary`; `anthropic`
  added to `telegram_bot/requirements.txt`; `.env.example` gains `ANTHROPIC_API_KEY=`.
- **Scripts** — `verify_slice5.py` (zero-spend, above) and `prove_slice5.py` (live proof, held).

### Deliberately NOT in this slice (per the approved plan)
Budget-governor enforcement (§4.10 — this slice writes actuals + an advisory estimate only, no
ceiling enforcement); Opus usage (PREMIUM tier wired but unused); a real web/trend research provider
(stays `UnavailableResearch`; `youtube_signal_research` remains a raising stub — **no OAuth
expansion**); the footage binder (Slice 4).

---

## Safety / conventions honoured
Channel-general (voice from config; wildlife is data). Secrets via `.env` (gitignored — confirmed
`.env` is NOT staged); the key is never printed/logged/committed. Build/prove on the Mac; VPS and
ocean stream untouched. Committed locally only (no push). The scoped, capped `ANTHROPIC_API_KEY` you
added is the human-gated spend control; the live run is the only remaining step and it waits on your
explicit go.

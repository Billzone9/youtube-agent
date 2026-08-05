# LLM backend without the Anthropic API — honest assessment (2026-08-05)

**Constraint:** Banks will not fund the Anthropic API. **This assessment does not pick — it lays out
what each alternative breaks, costs, and makes impossible, against the swappable provider layer.**

## The two facts that frame everything
1. **Vision is ~92% of Anthropic spend and is the hardest thing to replace.** A film's LLM cost is
   ~£0.72 vision (42 checks × 3 Haiku image-calls) + ~£0.008 text. Vision is BOTH the cost driver AND
   the quality gate (species/wild filtering — what stops off-subject, captive, or wrong-species footage,
   i.e. what makes the output non-templated). Text (scripts/descriptions) is cheap and comparatively
   easy to move.
2. **The bill is tiny — this is a PRINCIPLE, not a cost problem.** At full A′ cadence Anthropic is
   ~£4–5/month (≈£1.4 long-form vision + ≈£2.6 Shorts vision + pennies of text); right now it is ~£0.
   So "won't fund the API" rules out options that need *any* API spend, however small — and it means the
   vision-reduction levers save pennies, not pounds. Stated as fact, not to relitigate: the barrier is
   funding the API *at all*, so the decision is about capability, not amount.

## What the provider layer requires of ANY backend
The layer is genuinely swappable (`LLMProvider` Protocol, `LLM_PROVIDER` env-select) — a new backend is
a new provider class, not a rewrite of the writers. BUT the cost machinery we just built depends on what
a backend returns: `LLMResponse.usage` (real `TokenUsage`) + a stable `request_id`. These feed
`write_llm_cost` (idempotency `llm:{request_id}`), `usage_to_gbp`, the spend estimates/gates, and the
research reconciliation. **A backend that doesn't return real per-call usage + a stable id blinds all of
that.** And vision needs **image input** through the same interface (base64 blocks in `messages`).

---

## (a) Claude Code headless (`claude -p`) as the LLM backend
Shell out to the Claude Code CLI (Max subscription) instead of the API.
- **Acceptable use — the first blocker, not a footnote.** The Max subscription is licensed for
  interactive developer use. Driving it programmatically as the backend of a **commercial, automated,
  revenue-seeking pipeline** is very likely against Anthropic's terms and the Claude Code acceptable-use
  posture. The realistic downside is account suspension — and it would take Banks's *interactive* Claude
  access down with it. This is a real risk to weigh, not a technicality.
- **Blinds the cost machinery.** Even if `claude -p --output-format json` surfaces token counts, the
  *cost is subscription-flat* (£0 marginal), so the ledger/estimates/gates/ROI track nothing real; and a
  stable per-call `request_id` for idempotency is not guaranteed. The cost governor, spend gates, and the
  research reconciliation we just built become decorative.
- **Rate limits.** Max has message/usage caps (per-hour and weekly), shared with Banks's own use. A film
  is ~126 image-heavy vision calls + scripts; a cadence of films would hit those caps unpredictably and
  throttle both the agent and Banks.
- **Cannot run unattended (Banks's point).** `claude -p` needs the CLI installed and an authenticated
  interactive session on the host; tokens expire and need human re-auth. The agent's whole premise is
  24/7 unattended (scheduler, eventually the VPS). A backend that needs a logged-in interactive host
  breaks that.
- **Images are awkward.** Passing base64 frames through a CLI meant for interactive use is fragile vs. the
  clean image-block path the API provider uses.
- **Breaks / costs / impossible:** breaks the cost+gate+reconcile layer and unattended operation; costs
  £0 marginal but risks the subscription/account; makes honest cost accounting and clean 24/7 autonomy
  impossible, on shaky ToS ground.

## (b) Local model via Ollama — text, and separately vision
Zero API cost; runs on local hardware.
- **Text (scripts/descriptions/tags).** A local 7–14B model (Llama/Qwen/Mistral) via an `OllamaProvider`
  is technically straightforward against the layer. Quality is the risk: the house-voice standard + the
  AI-tell scanner + fact-underneath gates are tuned to Sonnet-class prose. A local model will clear them
  less often (more regenerations, or thinner prose) — assessable, but a real step down from the
  "genuine quality, not templated" bar. **Plausible with quality risk.**
- **Vision — the crux, and the honest answer is: probably NOT good enough.** Vision is 92% of the spend
  *and* the accuracy bottleneck. The gate must classify species + wild reliably enough to keep the
  footage on-subject. **Within-family discrimination is ALREADY unproven with Haiku** (BACKLOG: the
  definition-free gate reads a coyote as a grey wolf; only cross-family — lion-vs-wolf — is calibrated).
  A local vision model (LLaVA / Qwen-VL / Llama-3.2-Vision) is *weaker* than Haiku at fine-grained
  species/captivity distinctions, so it would sit **below a bar Haiku only marginally clears**. Honest
  read: local vision cannot meet the current gate's accuracy for anything beyond the most trivial
  subjects, and would let off-subject/captive footage through — degrading exactly the quality the gate
  exists to protect.
- **Hardware breaks cloud autonomy.** A usable vision + text model needs the Mac (the 2-core VPS cannot
  run them); renting a GPU costs money (also refused). So production becomes tethered to the Mac being
  on — the opposite of 24/7 cloud-autonomous. (Text-only local on the Mac is more tractable than vision.)
- **Cost machinery goes moot, not broken.** £0 marginal → the ledger records £0 for LLM; the spend
  gates/estimates/reconcile have nothing to govern. Not "broken," but the whole cost-governor investment
  becomes inert for LLM.
- **Breaks / costs / impossible:** breaks vision accuracy (the quality gate) and 24/7 cloud autonomy
  (tethers to local hardware); costs engineering (two Ollama providers + image plumbing) + local
  compute/electricity; makes reliable species discrimination at the current bar impossible, and makes the
  cost governor inert for LLM.

## (c) Reduce dependence — the four logged vision levers
Early-stop 1.2× (~15–20%), metadata pre-filter (~30–40%), 2-frames (~33%, needs recalibration), batch +
prompt-cache (~10–20%). Combined, realistically ~50–60% off vision → ~£0.30–0.35/film.
- **This is a mitigation, not a solution to a £0-API constraint.** It shrinks the bill but does not
  remove the need for *some* funded API. It only "solves" the problem if combined with either (a)/(b)
  (fewer calls → fewer rate-limit hits / less local compute) or a small funded budget.
- **The extreme version — near-zero vision — is a quality decision, not an engineering one.** You could
  push metadata/licence/keyword filtering hard and lean on Banks's end-review to catch mismatches,
  cutting vision to almost nothing. That is viable but it *lowers the quality bar* (more off-subject clips
  survive to the review), which is the thing the gate was built to prevent. That trade is Banks's to make.
- **Breaks / costs / impossible:** breaks nothing structurally; costs engineering for each lever; makes
  the *strict* vision bar cheaper but, pushed to the extreme, trades away the automated quality guarantee.

---

## The decision this comes down to (Banks's call — not made here)
The £0-API principle collides with the quality mission through the 92%-vision fact. The honest options,
none chosen:
1. **Text local (Ollama), vision stays a problem.** Move scripts/descriptions to a local model (accept a
   quality step-down); vision has no good local answer at the current accuracy bar.
2. **Relax the vision bar** (levers pushed hard + rely on end-review) so vision needs little/no model —
   trading automated quality for zero spend.
3. **A hard-capped, prepaid, vision-ONLY API key** (structural, like the ElevenLabs Music key: a fixed
   ~£5 prepaid cap the agent physically cannot exceed). This keeps the accuracy bar *and* the cost
   machinery, at a few pounds a month — but it is still "funding the API," which Banks has ruled out.
   Listed because it is the cheapest way to keep both quality and honest accounting; excluded if the
   principle is absolute.
4. **`claude -p`** — only if the ToS risk, the unattended-host requirement, and blinded accounting are
   acceptable; it keeps quality at £0 marginal but on shaky ground and not truly autonomous.

**The single question that decides it:** is the vision gate's accuracy negotiable? If yes → local/no
vision becomes viable (option 1/2), quality drops. If no → vision needs Haiku-or-better, which needs a
funded API (option 3), contradicting the constraint — and then `claude -p` (option 4) is the only
zero-fund path, with its ToS/autonomy costs. Banks decides; this assessment does not.

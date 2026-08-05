# Phase 1 — Anthropic cost estimate (BEFORE building)

**Why this exists:** vision (~£0.72/film, the current LLM cost driver) was omitted from the original
platform estimate entirely. Competitor/trend analysis and grounded research are both **new recurring
LLM spend** and neither has a cost model. This estimates each *before* a line is built, and decides —
per Banks — whether each needs a **spend gate** (a pre-spend check that can BLOCK) or just a ledger row.

**Prices (from `platform_settings.llm_pricing`, USD/Mtok in/out; FX USD→GBP 0.79):**
Haiku $1 / $5 · Sonnet $3 / $15 · Opus $15 / $75. Anthropic server-side web search ≈ $0.01/search.
Token counts below are **engineering estimates**, to be replaced by measured actuals after the first
runs (exactly how vision was calibrated to £0.017/check). All £ figures carry the project's **×3 lens**.

---

## A1 — Grounded research (per video)

**What one run does:** for a video's subject, a grounded pass produces the verified fact set the script
is built on (vivid surface, accurate fact underneath). Assumed an agentic loop: a few web searches +
synthesis. **Model: Sonnet** (facts underpin the script — Haiku too weak for fact-checking, Opus
overkill). If a separate grounded provider (e.g. Gemini) is chosen later, its cost replaces this; this
costs the **Anthropic** path Banks asked about.

**BOUNDED BY CONSTRUCTION — the estimate is a CEILING, not a hope.** An agentic loop with no cap is the
vision mistake reborn: the *rate* is right, the *volume* is unbounded — a stubborn subject could iterate
to 15+ searches and 90k input with nothing stopping it. So the loop has HARD CAPS enforced in code
(`cost._RESEARCH_MAX_*`), and the estimate is computed FROM those caps, so the run cannot exceed it:
| cap | value |
|---|---|
| max web searches | **8** (~6 expected) |
| max iterations (research rounds) | **4** |
| max cumulative input tokens | **60k** (2× the ~30k expected) |
| max output tokens | **6k** |

Hitting any cap is a **DECLARED degradation** (mirroring `AudioDesign.declared` from D3): research
**stops and ships with the facts gathered so far**, recorded in a research `declared` map — never more
spend. The feature imports the SAME constants the estimate uses, so estimate == enforced ceiling.

**Ceiling cost (Sonnet, the worst case the caps permit):**
| item | tokens | cost |
|---|---|---|
| input (cap) | 60k | 60k × $3/M = $0.180 |
| output (cap) | 6k | 6k × $15/M = $0.090 |
| web search (cap: 8 × $0.01) | — | $0.080 |
| **ceiling** | | **≈ $0.35 ≈ £0.28/video** (expected ~£0.17) |

The gate quotes the £0.28 ceiling, so a production can never be surprised by a runaway research loop.
*(Opus would ~2.9× this. Recommend Sonnet.)*

**How often:** once per video that gets research — long-form primarily (Shorts likely skip deep
research). At the A′ cadence (~2 long-form/mo) → **~£0.60–1.00/mo**; even weekly long-form → ~£1.30–2.00/mo.

**Gate? NO new gate — but it MUST go in the per-job estimate.** Grounded research is a per-video money
stage inside a production run, which already passes the production spend gate (`_spend_gate` →
`estimate_production_cost`, per-job threshold + rolling £200 ceiling). The one requirement, and it is
the exact vision-omission lesson: **add research to `estimate_production_cost`** so the existing gate
accounts for it, AND sequence it so the gate sees it (research must be inside/after the gate's estimate,
not spent during scripting *before* the gate fires). No new gate; a corrected estimate + correct ordering.

---

## §14.5 — Competitor & trend analysis (scheduled, per channel)

**What one run does:** fetch competitor/trend data (YouTube Data API — **quota**, not LLM spend) then an
LLM analysis pass → trend signals + "what to produce next" for the playbook. **Model: Sonnet** for the
judgment (Haiku is a cheaper fallback for pure summarisation).

**One run (Sonnet):**
| item | tokens | cost |
|---|---|---|
| input (≈10 competitors × ~20 videos' metadata + trends) | ~25k | 25k × $3/M = $0.075 |
| output (structured recommendations) | ~3k | 3k × $15/M = $0.045 |
| **total** | | **≈ $0.12 ≈ £0.095/run** → ×3 **budget £0.20–0.30/run** |

*(Haiku instead ≈ $0.04 ≈ £0.03/run → ×3 ~£0.10. Viable if analysis quality holds.)*

**How often:** "always-on" → scheduled. **Recommend WEEKLY per channel** (daily is 7× the cost for
trend shifts that don't move daily at this scale).
| cadence | Sonnet /mo/channel (×3) | at 10 channels (×3) |
|---|---|---|
| weekly | £0.41 (£1.20) | £4.10 (£12) |
| daily | £2.85 (£8.5) | £28.5 (£85) |

**Gate? YES — this is the category that needs one.** It is **unattended, scheduled, recurring** spend.
A ledger row records *after* the money is gone; that is too late for spend no human is watching. The
real risks are (a) **accumulation** (frequency × channels × time) and (b) a **runaway loop** (a retry or
an over-eager agentic analysis) burning budget with nobody present. So, before each scheduled run:
1. **estimate** the run (the cost model built first), then
2. **gate** it against the global £200 ceiling (month-to-date via `budget_status`) **and** a dedicated
   *unattended-analysis* monthly sub-budget, so trend spend can't silently crowd out production, then
3. **fail CLOSED** — if the budget is unreadable or would breach, **skip + alert**, never spend blind
   (the same posture as the recurring cadence gate). Reuse `_spend_gate` / `SpendGatePause` / `budget_status`.

---

## Bottom line (the decision Banks asked for)
| feature | one run (ceiling) | frequency | attended? | bounded? | needs a gate? |
|---|---|---|---|---|---|
| Grounded research | **£0.28 ceiling** (exp ~£0.17) | per long-form video | **yes** (in a production run) | **hard caps on the loop** (searches/iters/tokens) → cap = declared degradation | **No new gate** — add the ceiling to `estimate_production_cost`; the existing per-job gate covers it |
| Competitor/trend | £0.095/run | weekly per channel | **no** (scheduled) | batch size IS the bound (no loop) | **Yes** — pre-run, fail-closed budget gate + a dedicated sub-budget; not just a ledger row |

**Build order implication:** for BOTH, the **cost model (an `estimate_*` function + regression) is the
first artifact, before the feature** — so spend is estimated and gated from the first run, never
discovered in the ledger afterward. Trend analysis additionally needs the unattended-spend gate built
with it. Absolute £ are small today (pennies/run); the discipline is the point — no unattended,
un-estimated, un-gated recurring LLM spend.

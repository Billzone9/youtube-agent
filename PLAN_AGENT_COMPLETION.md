# PLAN — Finish the agent (evaluation + proposed sequence)

**Author:** Claude Code (engineer) · **For:** Banks's approval · **Date:** 2026-08-04
**Standing goal:** FINISH THE AGENT — every outstanding platform component — and make sure the code
works, BEFORE producing or publishing any further video. Correctness first, then build what's missing.
**Discipline in force:** capability may be BUILT, not EXERCISED for output; no publishing until Banks
says the build is done. No film-production runs. No ElevenLabs upgrade. Estimates are ×3-corrected.

This is a proposal. **Nothing is built until you approve the sequence.** You choose; I planned it.

---

## 1. Evaluation — does what's built actually work?

Three read-only surveys over ~8,600 lines (standards enforcement · Layer-A pipeline correctness ·
schema + harness). Headline, verified (not from memory):

**No blocking correctness defects in what exists.** The content and safety gates are real and
hard-fail: visual density (`density.py:assert_visual_density`), footage feasibility
(`feasibility.py:probe_feasibility`), the vision gate (three-way + self-checks), the audio noise
gate — **input AND output, and the output gate genuinely deletes a hissy render**
(`assembler.py:124-129`: `noise_gate` → `os.remove(out)` → raise), provider-error bodies carried
through on **all** providers incl. Pixabay (`pixabay.py:54`), and the public-artifact guard
(`metadata/guard.py`). Two "blocking" items a survey raised were **refuted on inspection** (Pixabay
and the noise gate are both correct) — recorded here because "verify, don't assume" is the rule.

### Real defects found — all backlog-tier, none corrupts published output
| # | Defect | Where | Class |
|---|---|---|---|
| D1 | **Verify scripts leave DB debris** — ~12 of 18 don't self-clean; this is the root cause of the 32-approval pile just voided. `verify_cohort_playlist.py` is the good pattern (finally-block DELETE). | `scripts/verify_*.py` | backlog (cheap, high-value) |
| D2 | **Produce jobs never reach a clean terminal status** — they rest at `assembling`/`assembled` forever; the resume query `status='assembling' AND stage<>'submitted'` is fragile; a crash at `stage='submitted'` won't resume. Made the stuck-job pile hard to read. | `produce.py:447`, `scheduler/runner.py:109`, migration 0004 semantics | backlog |
| D3 | **Audio design can silently degrade** — `_design_from_disk` returns a partial design if some cue files are missing; no assertion that expected music exists → a film could assemble with less audio than intended. | `produce.py:404-423`, `audio_design.py` | backlog |
| D4 | **Alt production paths aren't resumable** — `produce_from_sourced` / `remake_from_narration` fail permanently on a money-stage crash (the scheduler's `produce_video` path IS resumable; these aren't). | `produce.py:711-795` | backlog |
| D5 | **No CI** — `make health` (17 offline + 1 live verify) answers "is the agent healthy" locally, but nothing gates commits; no `pyproject.toml`/pytest/Actions. | repo root | backlog |

### Brief corrections (BRIEF_PLATFORM_COMPLETION.md predates this session — these are STALE)
- "No single health command" → **stale.** `make health` exists (17 offline + 1 live).
- "Assembly is 16:9 only / native Shorts not built" → **stale.** 9:16 is first-class; `produce_short`
  + binder + Shorts density + publish gate + cohort + cadence wiring were built this session (capability;
  parked from exercise).
- §1 ElevenLabs allowance (recurring vs rollover) → **resolved** (recurring=30k inference + regression);
  the 27-Aug live re-read remains a cheap confirmation.
- "Provider layer not proven for footage" → **stale.** Footage is swappable (Pexels + Pixabay).
- Survey's `video_metrics`/`revenue_ledger` "BLOCKING" → **reclassified.** They're *unbuilt features*
  (B4/B7), not defects in existing code.

---

## 2. Component status, re-evaluated against `main`

| # | Component | State now | Verifiable without publishing? |
|---|---|---|---|
| 1 | A1 grounded research | not built (`research.py` degrades honestly) | ✅ yes |
| 2 | B1 channel onboarding interview | not built | ✅ yes |
| 3 | B4 learning loop | schema fit; `upsert_metrics` never called; **needs analytics scope** | ⚠️ via the 2 already-public films + new scope |
| 4 | B5 no-code dashboard | not built | ✅ yes (surfaces existing state) |
| 5 | B6 marketing / promotion | not built | ❌ payoff is publishing/ROAS — **the stopped arc** |
| 6 | B7 monetisation + revenue | `revenue_ledger` dormant + **missing `video_id`** | partial (product discovery yes; revenue data no) |
| 7 | B8 safety / compliance | **partly exists piecemeal** (claim-safe, disclosure, noise, vision) | ✅ yes (consolidate + fill) |
| 8 | Native Shorts / multi-format | **BUILT this session** (capability, parked) | — done |
| 9 | MLA multilingual dubbing | not built | ❌ exercise needs publishing |
| 10 | Social cross-posting | not built | ❌ exercise is external posting (gated) |
| 11 | Comment & community | not built | ❌ nothing to moderate at 0 engagement |
| 12 | Competitor & trend analysis | not built | ✅ yes (reads external public data) |

**Key lever:** "make sure the code works" requires we can TEST each thing. So sequence by
*verifiable-now-without-publishing* first; build-then-park the rest; defer the publishing-only arc.

---

## 3. Proposed sequence

### Phase 0 — Correctness & trust *(make the code provably work first)*
D1 self-cleaning verifies (kill the debris at the source) · D2 produce-job terminal status + resume-query
fix · D3 audio-design completeness guard · D5 CI wrapper (`make health` on an ephemeral Postgres +
`pyproject.toml`). D4 either fixed or explicitly routed through the resumable path.
*Why first:* it's Banks's stated priority, it's cheap, and every later component lands on a trustworthy
base behind a green gate.

### Phase 1 — The control surface *(see & understand what exists)*
B5 dashboard **skeleton**, read-only: channels · jobs · cost ledger + ROI · approvals queue · audit
timeline · playbooks. No new backend — it surfaces the rich data already captured.
*Why here:* it's the "be in control and understand how it works" surface you asked for, and it makes
every later component observable as it lands.

### Phase 2 — Intelligence that needs no publishing *(verifiable now; improves what's PRODUCED)*
#12 competitor & trend analysis (feeds playbook + dashboard) · #1 A1 grounded research (real facts into
scripts + Layer-1 descriptions) · B8 safety/compliance **consolidation** (cross-video variation
enforcement, YMYL handling, disclosure/claim-safe as one auditable layer).
*Why here:* all verifiable now, all raise quality/safety of output without publishing anything.

### Phase 3 — General platform + analytics *(build; verify on assets that are ALREADY public)*
#2 B1 onboarding interview (per-channel config → unlocks channel #2) · #3 B4 learning loop: add
`youtube.analytics.readonly` (**security review on `youtube.py` + fresh consent**), analytics client,
`video_metrics` write path, correlation — **verified by pulling REAL analytics for the two already-public
films, no new publishing.**
*Why here:* B4 is exercisable now via the existing public videos; onboarding makes it truly multi-channel.

### Phase 4 — Build-now / exercise-later *(capability built + offline-verified; output parked)*
#6 B7: fix `revenue_ledger` (add `video_id` attribution) + product/affiliate discovery (verifiable now);
real revenue tracking parked until monetisation · #9 MLA dubbing · #10 social cross-posting · #11
comment/community — each built and offline-verified; **exercise stays behind the publishing gate.**

### Deferred indefinitely
**B6 marketing / promotion** — the arc just stopped; its payoff is publishing/ROAS. Resume only when
the build is done AND Banks decides to publish.

---

## 4. Honest estimate (×3-corrected)
| Phase | Focused working blocks |
|---|---|
| 0 — correctness & trust | 2–3 |
| 1 — dashboard skeleton | 2–4 |
| 2 — intelligence (×3 components) | 4–6 |
| 3 — onboarding + B4 (incl. scope/consent/review) | 4–6 |
| 4 — build-park (×4 capabilities) | 5–8 |
| **Total** | **~17–27** |

Biggest uncertainties: dashboard scope (skeleton vs. full control surface); analytics-scope consent
friction + its security review; how deep B8 variation enforcement goes. I'll re-estimate each phase at
its start with the ×3 lens.

---

## 5. Decisions I need from you (not now-blocking, but they shape phases)
1. **Approve this sequence** (or reorder). I recommend Phase 0 first regardless.
2. **Dashboard scope** — start with the read-only skeleton (my recommendation) or aim fuller?
3. **Analytics scope** — when we reach Phase 3, approve adding `youtube.analytics.readonly` (new consent
   + a `youtube.py` breadth review). Flagging now so it's not a surprise.
4. **Confirm the defers** — B6 indefinite; exercise of #9/#10/#11 parked behind publishing. Say if any
   of those matters sooner.

I disagree with nothing material in the brief except the stale items in §1 above; its core ask —
correctness first, then build, defaulting defects to backlog — is right and is what this plan does.

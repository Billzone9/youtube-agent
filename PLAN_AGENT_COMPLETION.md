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

## 3. Proposed sequence — APPROVED 2026-08-04 with three adjustments (folded in below)
Banks's adjustments: (1) dashboard moves to LAST — it's a *view of* the agent, not part of it, and it
would display components that don't exist yet; (2) Phase 4 must justify each component — build it only
if "done" is definable WITHOUT running it, else defer with a named trigger (four honest defers beat four
unverifiable capabilities); (3) **D1 goes first** — a verify suite that pollutes production state is what
armed 32 publish cards; that is a latent accidental-upload path, not hygiene. Make **hermetic-by-default
the standard for every new verify.**

### Phase 0 — Correctness & trust *(make the code provably work first)*
- **D1 FIRST, before anything else.** Every verify self-cleans (no production-state debris), and
  hermetic-by-default becomes a written, enforced standard for all new verifies — because a polluting
  test suite is an accidental-upload path, not hygiene. This is the literal first task.
- Then: D2 produce-job terminal status + resume-query fix · D3 audio-design completeness guard · D5 CI
  wrapper (`make health` on an ephemeral Postgres + `pyproject.toml`). D4 fixed or explicitly routed
  through the resumable path.
*Why first:* Banks's stated priority; cheap; every later component lands on a trustworthy base + green gate.

### Phase 1 — Intelligence that needs no publishing *(verifiable now; improves what's PRODUCED)*
#12 competitor & trend analysis (feeds playbook) · #1 A1 grounded research (real facts into scripts +
Layer-1 descriptions) · B8 safety/compliance **consolidation** (cross-video variation enforcement, YMYL
handling, disclosure/claim-safe as one auditable layer).
*Why here:* all verifiable now, all raise quality/safety of output without publishing anything.

### Phase 2 — General platform + analytics *(build; verify on assets that are ALREADY public)*
#2 B1 onboarding interview (per-channel config → unlocks channel #2) · #3 B4 learning loop: add
`youtube.analytics.readonly` (**security review on `youtube.py` + fresh consent**), analytics client,
`video_metrics` write path, correlation — **verified by pulling REAL analytics for the two already-public
films, no new publishing.**
*Why here:* B4 is exercisable now via the existing public videos; onboarding makes it truly multi-channel.

### Phase 3 — Monetisation capability *(only the verifiable-now parts; rest deferred with a trigger)*
#6 B7, split honestly:
- **BUILD NOW (verifiable):** product/affiliate **discovery** — given a niche, find claim-safe fitting
  products, rank, log provenance; "done" = offline test on a fixture catalog + a real query returns
  ranked candidates. And the `revenue_ledger` **schema fix** (add `video_id` attribution) + write path,
  verified with fixture/manual rows.
- **DEFER (named trigger):** real revenue INGESTION (AdSense/affiliate/sponsorship figures). Trigger:
  *when the channel is monetised (AdSense approved) or an affiliate program is joined* — there is no
  revenue data to prove against until then.

### Phase 4 — The control surface *(LAST — a view built once there's something to show)*
B5 dashboard **skeleton**, read-only: channels · jobs · cost ledger + ROI · approvals queue · audit
timeline · playbooks · trend signals · learning-loop output. Built last, so it surfaces components that
actually exist.
*Why last (Banks's call):* the dashboard is a window onto the agent, not the agent; finishing the agent
comes first.

### Deferred with named triggers *(honest defer beats unverifiable capability — Banks's adjustment 2)*
Each states what would make it real; none is built now because none can be verified without publishing/
engagement that is currently parked.
- **B6 marketing / promotion (#5).** Trigger: *build complete AND Banks decides to publish* (payoff is
  publishing/ROAS — the arc just stopped).
- **MLA multilingual dubbing (#9).** Trigger: *audience data justifies 1–2 launch languages AND
  publishing resumes.* Languages are meant to be data-driven (roadmap); at 0 subs there is no data, and
  the multi-track attach needs a real `videos.insert`. Premature to build blind.
- **Social cross-posting (#10).** Trigger: *a channel opts in to a specific platform AND publishing
  resumes.* Wildlife is YouTube-only by default; no channel wants it yet, and a post can't be verified
  without posting. Nothing to build against.
- **Comment & community management (#11).** Trigger: *published videos accumulate real comments (needs
  the comment/analytics scope) — i.e. after publishing resumes.* At ~0 engagement there are no comments
  to read, draft against, or moderate; a drafter with no real inputs is unprovable.

*Note:* "finishing the agent" therefore means — everything verifiable-now is BUILT and PROVEN; everything
that inherently needs publishing/engagement is DEFERRED with an explicit trigger tied to the publish
decision. That is the honest definition of done under the build-first discipline.

---

## 4. Honest estimate (×3-corrected)
| Phase | Focused working blocks |
|---|---|
| 0 — correctness & trust (D1 first) | 2–3 |
| 1 — intelligence (×3 components) | 4–6 |
| 2 — onboarding + B4 (incl. scope/consent/review) | 4–6 |
| 3 — monetisation capability (discovery + ledger fix) | 2–3 |
| 4 — dashboard skeleton (last) | 2–4 |
| **Total** | **~14–22** |

(Lower than the first pass: three Phase-4 capabilities became honest defers instead of build work.)
Biggest uncertainties: analytics-scope consent friction + its security review; how deep B8 variation
enforcement goes; dashboard scope. I'll re-estimate each phase at its start with the ×3 lens.

---

## 5. Decisions already made / still open
- **Sequence — APPROVED** (with the three adjustments folded in above). Start Phase 0 at D1.
- **Dashboard scope** — read-only skeleton, built LAST. (Open: whether to go fuller once we're there.)
- **Analytics scope** — Phase 2 will need approval to add `youtube.analytics.readonly` (new consent + a
  `youtube.py` breadth review). Flagged now; not yet actioned.
- **Defers confirmed** — B6 (trigger: publish decision), MLA / social / comments (triggers above).

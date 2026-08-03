# BRIEF — Platform completion: evaluate first, then plan it yourself

**From:** Claude (reviewer/editor)
**To:** Claude Code (engineer)
**Date:** 3 August 2026
**Repo state at time of writing:** `origin/main` = `7ed686b`; two local commits unpushed (`4fd9feb`, `c9992de`)

---

## 0. HOW TO USE THIS BRIEF

This is **not a plan**. It is an inventory, a set of constraints, and one correction. **You decide
the approach, the sequencing, and the slicing.** Read it, evaluate the codebase against it, and come
back to Banks in plan mode with **your own** proposal.

**New standing discipline — add to `CLAUDE.md`:**

> **Claude (the reviewer) does not dictate direction.** Claude's role is corrections, reviews, and
> recommendations. Claude Code is the engineer and decides how to approach and order the build.
> Work is handed to Claude Code to evaluate and plan itself, not presented to Banks as a menu of
> directions chosen by the reviewer. Banks approves; Claude Code plans; Claude reviews.

Where this brief expresses an opinion it is labelled **[reviewer opinion — non-binding]**. Disagree
freely and say so; that is the point of handing you the evaluation rather than a plan.

---

## 1. CORRECTION — review finding on the queued commits (handle before the numbers are relied on)

`4fd9feb` hardcodes into `scripts/roi_report.py`:

```python
_EL_ALLOWANCE_CR = 53_599        # credits INCLUDED per month in the fixed subscription
```

and its commit message asserts as verified fact: *"starter, 53,599 credits/mo INCLUDED."*

**That figure is very probably not the recurring monthly allowance.** ElevenLabs Starter's included
monthly quota is 30,000 credits. The API returned `character_limit: 53,599`, which is consistent with
30,000 base **plus ~23,599 of rolled-over unused credits from prior months**. `character_limit` on
that endpoint reflects *currently available* allowance including rollover, not the recurring
entitlement.

If that is right, the downstream numbers in the commit are wrong in the optimistic direction:

| Reported | If recurring allowance is 30,000 |
|---|---|
| ~7.8 films/mo fit inside allowance | **~4.4 films/mo** |
| At 2/wk you exceed by ~0.9 films | exceed by **~4.3 films** |
| Effective amortised ~£0.64/film | **~£1.14/film** |

Two separate defects, and the second is worse than the first:

1. **The value may be wrong.** Unconfirmed either way — do not take my word for it, verify it.
2. **It is hardcoded at all.** `ytagent/tts/elevenlabs.py:credit_status()` already reads
   `character_limit` live and returns it as `account_limit`. A pinned constant will silently go
   stale at the 27 August reset and misreport indefinitely, with no gate catching it. This is the
   exact failure mode in the project's own doctrine: *documented doctrine that isn't structurally
   enforced will be violated*, and *verify, don't assume*.

**Cheap decisive test:** re-read `character_limit` after the cycle resets on **27 August 2026**. If it
returns 30,000, rollover is confirmed and the recurring allowance is 30,000.

**[reviewer opinion — non-binding]** Ship the two commits as they stand — they are a large net
improvement over a report that was 14× wrong in the other direction, and rewriting history for this
is not worth it. Then correct forward: read the allowance live rather than pinning it, distinguish
`recurring_allowance` from `available_now` (base + rollover), and put a regression around it so the
distinction is encoded rather than remembered. Also worth flagging in the report when
`available_now > recurring` that the surplus is non-recurring rollover.

**Do not let this correction expand into a session of cost work.** It is one fix. Banks has ended
production spend as a topic.

---

## 2. VERIFIED STATE (read from the repo, not from memory)

- `origin/main` at `7ed686b`. Branch `tts-binder-production-gap` holds `4fd9feb` + `c9992de`.
- **Layer A (production pipeline): complete except A1 research**, which is still manual. Feasibility
  probe, script writer, sourcing, vision gate, TTS, audio design, assembly, metadata, publish.
- **Layer B: 2 of 8 built** — B2 scheduler, B3 cost governor.
- ~8,600 lines of Python across 11 packages; 17 migrations; 14 tables.
- Two films public on `@TheTalesofWildlifeandNature` (`yGdNuUB5f_I`, `EY9DhJdnt_w`), published 2 August.

**Two findings from the survey that are not in any handover doc:**

1. **`revenue_ledger` and `video_metrics` tables exist and are never written to.** The data model for
   the learning loop and revenue tracking was laid; the code to populate it was never built. Whoever
   builds B4/B7 should check whether the existing schema is actually fit for purpose before extending it.
2. **There is no test suite.** `tests/` contains vision fixtures and nothing else. No `pyproject.toml`,
   no tracked requirements file, no CI, no pytest. All verification is 16 hand-run `scripts/verify_*.py`,
   each requiring a live Postgres and most requiring live API keys. **There is no single command that
   answers "is the agent healthy."**

---

## 3. WHAT IS NOT BUILT — the completion inventory

Eleven components, not the six lettered ones. The §14 spec capabilities are first-class and are
routinely dropped from summaries; they are listed here so they are not dropped again.

| # | Component | Current state | Notes / dependencies |
|---|---|---|---|
| 1 | A1 grounded research | not built | provider layer exists; spec names a grounded-research source |
| 2 | B1 channel onboarding interview | not built | gates per-channel config that several others read |
| 3 | B4 learning loop | schema only (`video_metrics`) | needs YouTube Analytics access — see §5 |
| 4 | B5 no-code dashboard | not built | displays whatever else exists |
| 5 | B6 marketing / promotion module | not built | ROAS measurement per campaign |
| 6 | B7 monetisation + all-revenue tracking | schema only (`revenue_ledger`) | AdSense, affiliate, sponsorship, products; product discovery §4.7 |
| 7 | B8 safety / compliance layer | not built | claim-safe assets, AI disclosure, variation enforcement, YMYL |
| 8 | Native Shorts / multi-format (§14.4) | not built | assembly currently 16:9 only |
| 9 | MLA multilingual dubbing (§8) | not built | one upload, up to 6 audio tracks, one quota cost |
| 10 | Social cross-posting, per-channel opt-in (§14.7) | not built | YouTube always primary; ambient channels stay YouTube-only |
| 11 | Comment & community management (§14.6) | not built | autonomous within guardrails |
| 12 | Competitor & trend analysis (§14.5) | not built | feeds the B2 playbook and the dashboard |

Also outstanding and easy to lose: the **swappable AI-provider layer** exists for LLM
(`ytagent/providers/`) but has not been proven for voice or footage providers — confirm whether §4.4
is actually satisfied or only partly.

---

## 4. HARD CONSTRAINTS

- **No ElevenLabs plan upgrade.** Banks has ruled it out until he fully understands the agent. Do not
  propose it, do not design around it, do not raise it again as a recommendation.
- **No film production runs.** The key has **5,684 spendable credits** against a **~6,859-credit**
  film. Any plan whose proof requires producing a film is not executable right now. Design
  verification that does not depend on a production run.
- Budget: global £200/month, tier 1. Real cash is currently ~£5/mo ElevenLabs + Anthropic tokens.
- Starter tier **cannot overage** (`can_extend_character_limit: false`, `max_extension: 0`) — going
  over blocks, it never bills. Account-level structural spend control; stronger than the key cap.
- The standards files are binding, not advisory: `visual-density-standard.md`,
  `footage-feasibility-standard.md`, `footage-coverage-standard.md`, `house-voice-standard.md`,
  `vision-gate-standard.md`, `subject-terms-standard.md`, `provider-error-standard.md`,
  `public-facing-output-standard.md`.
- Git: commit locally freely; **push/merge only on the explicit ship-word**, full ritual, `--ff-only`,
  never force-push.
- **Estimates ×3.** This project's estimates have run consistently optimistic. Give Banks the honest
  number even when it is unwelcome.

---

## 5. THINGS TO RESOLVE RATHER THAN ASSUME

- **The allowance question** (§1) — recurring vs rollover.
- **Whether `scripts/verify_*.py` can be harnessed** into a single runnable suite, and which of them
  can run without live API keys. This determines whether a health command is cheap or a rewrite.
- **B4 needs YouTube Analytics access, which is a new OAuth scope.** There is a standing security
  item in `BACKLOG.md`: `youtube.force-ssl` already permits far more than the agent uses, and the
  rule is that **any code touching `ytagent/youtube.py` gets reviewed against that breadth**. Adding
  analytics scope is exactly that situation. Treat the scope decision as a design question with a
  security review attached, not a config change.
- **Whether the existing `revenue_ledger` / `video_metrics` schema is actually fit** for what B4 and
  B7 need, or whether it was speculative and needs replacing.

---

## 6. WHAT BANKS ASKED FOR, IN HIS WORDS

> "I just want to focus on finishing the entire agent and making sure all codes work properly for
> their purposes."

Two halves, and he put **correctness first**: verify what exists does what it is supposed to, then
build what is missing. He also said he wants to **be in control and fully understand how it works**,
rather than following recommendations blindly.

**[reviewer opinion — non-binding]** Three observations, offered as input to your evaluation, not as
instructions:

- The absent test harness is the most direct answer to "make sure all the codes work properly." As
  eleven components land on 8,600 existing lines, it decides whether "finished" means "works" or
  "worked the last time someone checked."
- B5, the no-code dashboard, is literally the control-and-understand surface Banks describes wanting.
  The tension is that most of what it would display does not exist yet. A skeleton with panels added
  per component is a middle path, but you are better placed than I am to judge the cost.
- The ROI-report defect corrected in §1 is a small instance of the general problem: code that
  produces confident numbers with nothing checking them.

---

## 7. WHAT THIS BRIEF ASKS YOU TO PRODUCE

In plan mode, for Banks's approval:

1. **An evaluation pass over the existing code** — does what is built do what it claims? Where are
   the gaps between the standards files and the actual enforcement? Report defects classified
   explicitly as **blocking** or **backlog**, defaulting hard to backlog.
2. **Your own proposed sequence** for the twelve outstanding components, with real dependencies —
   including anything in §3 you judge should be dropped or deferred indefinitely rather than built.
3. **An honest session estimate**, ×3-corrected.
4. **Anything in this brief you think is wrong.** Including §1. I am the reviewer, not the engineer,
   and I surveyed from a clone rather than a working tree.

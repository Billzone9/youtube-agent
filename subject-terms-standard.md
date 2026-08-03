# Subject-terms standard — a playbook subject is a SEARCH term, and must be UNAMBIGUOUS

Established 2026-08-03 from the 2nd supervised scheduler run.

## The rule
A subject stored in a playbook's `subject_pool` is not a topic label — it is the **search term** that
seeds every sourcing query. It must therefore be **unambiguous**, not merely correct. A polysemous term
poisons the pool with the wrong meaning:

- `"lion"` sourced **10 clear** — because it also matches **sea lion**, **mountain lion**, **lion
  sculpture/statue**, and captive lions. 19 of the run's 23 vision "contradictions" were pinnipeds
  ("sea lion", "seal", "walrus"); 3 were "lion (sculpture)". The species gate rejected them correctly;
  the term was the problem.
- `"African lion"` / `"lioness pride savanna"` names the wild plains cat unambiguously.
- `"African elephant"` is already unambiguous — which is one reason it sourced 54 clear.

## Ambiguity is NOT scarcity
Two different failures must be told apart before a subject is written off:
1. **Ambiguous term** (fixable): the library is full of the subject, but the term pulls homonyms /
   captivity. → Disambiguate the term; store the disambiguated form in the pool.
2. **Thin library** (nothing to do): the wild footage genuinely isn't there (a rare species/biome).

The pool-vetting step (`scripts/vet_pool.py`) distinguishes them: a subject that yields low is RE-PROBED
with a sharper term before being discarded. If the sharper term's yield jumps, it was ambiguity (case 1)
and the disambiguated term is what gets stored; if it stays low, it's scarcity (case 2).

## How it's enforced
- **Vetting** measures coverage per candidate + auto-disambiguates underperformers, and writes the
  pool **ordered most-coverage-first with the disambiguated terms** — so the scheduler tries the
  best-covered subject first (advisory ordering; still only rejected by real sourcing + the E<5 floor).
- **Doctrine:** never hand the playbook a bare polysemous animal name; store the wild/African/context-
  qualified form. Curate pools from vetting evidence, not from what merely sounds coverable.

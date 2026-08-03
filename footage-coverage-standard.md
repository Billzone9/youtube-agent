# Footage-coverage standard — what free stock libraries actually hold, and how it shapes every subject

Companion to `footage-feasibility-standard.md`, `subject-terms-standard.md`, `visual-density-standard.md`,
`vision-gate-standard.md`. Established 2026-08-03 from four supervised scheduler runs + a pool-vetting
pass. This is **not a defect report — it is a discovery about what this platform can make.** It is a
structural constraint on the whole channel and it shapes every future subject decision. Read it before
adding any wildlife subject to a playbook pool.

## The finding
Free/claim-safe stock libraries (Pixabay, Pexels and the like — the only footage we may use) do **not**
stock the animal kingdom evenly. For our purposes they fall into three coverage classes, and **only one
class yields a makeable wild-documentary film**:

1. **Deep AND wild-dominated — the sweet spot (rare).** A large, well-stocked pool that is
   overwhelmingly *wild* footage. The film sources easily. **The African elephant is the one proven
   member:** pool depth E≈157, wild-dominated → **54 clear** clips in a single footage-led source. It is
   deep-stocked *and* mostly filmed in the wild (safari/reserve footage dominates over zoo footage).

2. **Deep BUT captive-polluted (most charismatic megafauna).** A large pool whose footage is mostly
   **captive** — zoo, safari-park, enclosure — which the wild-gate correctly rejects. The pool looks
   healthy on a shallow probe and then collapses at real source:
   - **Lion** — sourced only **10 clear**. (Compounded by homonyms: "sea lion", "lion statue" — see
     `subject-terms-standard.md`. But even *"African lion savanna wild"* got ~6/20 wild: the rest were
     **captive lions**, not sea lions. Disambiguation fixes the homonym, not the captivity.)
   - **Giraffe** — its rejects were `species=clear_match, wild=clear_mismatch`: **zoo giraffes**,
     correctly rejected by the wild-gate. An optimistic ~7/10 probe ratio collapsed on the deep source.

3. **Genuinely wild BUT thin (herd animals).** ~100% wild footage but a shallow pool — too few clips to
   fill a film at house visual density.
   - **Zebra** E≈8, **wildebeest** E≈13 — both wild-dominated, both too shallow to source a full film.

## Why this is structural, not a bug
Across the runs the **scheduler behaved correctly every time** — it proceeded past noisy probe verdicts,
ran the real source, recorded the true clear counts, capped consecutive sourcing failures at 3, and
paused + alerted. Nothing in the code is wrong. The binding constraint is **the composition of the free
libraries themselves**: they were filmed by whoever filmed them, and for most non-elephant megafauna
that means zoos. No scheduler change moves this — only subject choice and curation do.

## Doctrine (how this shapes subject decisions)
- **Expect most charismatic non-elephant megafauna to fail on captivity, not scarcity.** A big pool is
  NOT evidence of a makeable film — it can be a big pool of zoo footage. Only *wild-dominated* depth counts.
- **Disambiguation (`subject-terms-standard.md`) fixes homonyms; it does NOT fix captivity.** Sharpening
  "lion" → "African lion savanna" removes sea lions but leaves captive lions. Both filters must pass.
- **Curate pools from vetting evidence** (`scripts/vet_pool.py`), and read its `wild` ratio, not just its
  yield estimate — a shallow probe over-counts because it samples the top-ranked (often the cleanest)
  clips first. The real gate is always `source_film`'s clear count.
- **The viable pool for this channel is NARROW.** Do not assume a subject is coverable because it is
  famous or the library is large. The candidates most likely to join the elephant in class 1 are animals
  that are *abundantly filmed in the wild and rarely in captivity* — large-range wild fauna, birds in
  flight, marine life, landscape-scale herds shot from the air. Each must be proven by vetting, never assumed.
- **When no class-1 subject is available, the honest move is to widen the library search or the niche —
  not to force a captive-polluted subject through.** A thin/captive source yields a sparse or mismatched
  film that the density and wild gates will (correctly) reject downstream anyway.

## Evidence (the four supervised runs + vetting)
| subject | class | pool E | wild coverage | real source | outcome |
|---|---|---|---|---|---|
| African elephant | 1 deep+wild | ~157 | wild-dominated | **54 clear** | the one makeable subject |
| Lion / African lion | 2 captive-polluted | large | ~6/20 wild even disambiguated | **10 clear** | SOURCING_SHORT |
| Giraffe | 2 captive-polluted | moderate | zoo-dominated (`wild=clear_mismatch`) | ~0 clean | SOURCING_SHORT |
| Zebra | 3 wild-but-thin | ~8 | ~wild | too few | shallow pool |
| Wildebeest | 3 wild-but-thin | ~13 | ~wild | too few | shallow pool |

The lesson cost ~four hours of real sourcing to establish. It is written here so no future session
rediscovers it by burning another four.

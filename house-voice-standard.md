# House-voice standard

Canonical philosophy for how the agent WRITES — narration scripts and the prose of public
descriptions — across every channel. This doc is the *why*; the enforceable source of truth is the
code (`ytagent/authoring/style.py`, `ytagent/authoring/tells.py`), which cites this doc's sections,
exactly as `ytagent/metadata/guard.py` cites `public-facing-output-standard.md §3`. Read this before
changing any writing behaviour. It is distinct from the **public-facing output standard** (what an
audience *sees*: no internal artifacts, SEO, disclosure); this doc governs the *craft of the prose*.

## §1 — The register (positive)
The house voice, established by the lion film, is **poetic on the surface, accurate underneath**:
matured, unhurried, vintage-documentary; it paints the scene an image at a time and lets meaning set
the rhythm. Channel-general principles (the *voice* differs per channel; the *craft* does not):

- **Write to the footage.** Every line earns its place beside a shot. Prefer the concrete, seen
  detail over abstraction; the words serve the picture, never decorate it.
- **Fact underneath, poetry on top.** Every claim is accurate and defensible. Lyricism heightens the
  truth; it never invents one. Uncertain facts are flagged, not smoothed over.
- **Earn cadence, don't manufacture it.** Repetition, the short sentence, the held pause — these
  arise from meaning. They are tools of emphasis, not a template to fill.
- **Restraint.** Silence and the plain sentence are instruments. Not every line needs ornament; the
  quiet line makes the vivid one land.
- **Per-channel voice from config.** The channel's `VoiceBrief` (tone, purpose, narrator style) sets
  the register. The lion's reverent poetry is the *wildlife instance*, not the universal template — a
  kids' channel or a finance channel reads nothing like it, and the same code must produce that.

## §2 — The AI tells (negative), and why we calibrate, not ban
The failure mode is prose that reads as machine-made. But the tics that mark AI writing are often the
*same devices* the house voice uses deliberately — the lion narration is dense with em-dashes and
rule-of-three cadences, and they are its music, not its flaw. **So we never ban a device by
presence.** We flag **overuse relative to the exemplar's own baseline**, plus a short list of tics
the house voice never commits.

Measured lion baseline (`lion-doc-01-narration.md`): **2.50 em-dashes per 100 words, 0 exclamation
marks.** The scanner's acceptance test is that it treats the lion as clean
(`scan_tells(<lion narration>).flagged is False`). If it ever flags the lion, the thresholds are
wrong — not the lion.

**Gated (flag → regenerate):**
- em-dash density *above* the house baseline (overuse, not use);
- exclamation marks (the documentary register uses none);
- "not only … but also" scaffolding;
- generic explainer openers ("In this video…", "we'll explore", "Have you ever wondered",
  "Welcome back", "today we're going to").

**Advisory (reported, never gated):**
- rule-of-three density — the house voice uses tricola on purpose; surfaced as a number for human
  eyes, never a pass/fail;
- LLM lexical crutches ("delve", "tapestry", "testament to", "nestled", "it's important to note",
  "ultimately", "moreover/furthermore" as filler, "a symphony of", "when it comes to") — counted and
  surfaced.

## §3 — Enforcement is advisory, and never edits prose
The tell-scanner **flags**; it does not rewrite. On a flag the writer *regenerates* (up to a small N)
and, failing that, surfaces the text and the report to Banks. Silently editing prose would hide the
tell and can mangle the very voice we are protecting. (This is the opposite of `guard.py`, which is a
hard publish-gate that *refuses* — because an internal-artifact leak is a safety failure, whereas an
AI tell is a quality judgment.)

## §4 — Versioned for the learning loop
The style spec, the banned-tics list, and the scanner thresholds are versioned
(`STYLE_SPEC_VERSION`, `TELLS_THRESHOLDS_VERSION`), and every generated artifact is stamped with the
versions + model + params it was produced under. When the Layer-2 performance loop comes online it
can correlate voice/prompt revisions against real audience response and tune the writer — the record
is being kept now, as the ledgers were laid before their features.

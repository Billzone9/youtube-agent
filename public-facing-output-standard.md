# Public-facing output standard

Canonical doctrine for everything an audience sees, across every channel and platform. This is the
full specification; `youtube-agent-spec.md` §15 summarises it and points here, and `CLAUDE.md`
carries the condensed operating note. Read this file in full before building or changing any
metadata/description behaviour.

Everything an audience sees must be **viewer-first, on-brand, and free of internal engineering
artifacts** — and metadata is a **growth lever written with research and improved with evidence**, not
a fixed template.

## 1. The doctrine (applies to ALL public-facing output)
- **Scope.** Descriptions, titles, tags, chapter labels, any text baked into thumbnails, community
  posts, and social captions — anything an audience sees, on YouTube or any cross-posted platform.
- **Viewer-first and on-brand.** Written for the audience of that specific channel, in that channel's
  voice, to inform, attract, and retain — never as a by-product of the build process.
- **HARD RULE — no internal artifacts, ever.** No filenames, repo paths, manifest references (e.g.
  `lion-doc-01-footage-manifest.md`), job or video IDs, QC numbers, LUFS/byte figures, internal
  status labels, or any engineering detail may appear in public-facing text. The agent keeps the
  **internal provenance/audit record** and the **public text** as two entirely separate things: the
  public text is *authored*, the internal record is *logged*, and they never bleed into each other.
  (This is the fix for the manifest-filename leak on the lion upload — see §3.)
- **Honest and compliant.** Accurate claims only; required synthetic-content/AI disclosure present
  (§2); no clickbait that misrepresents the content — that both misleads viewers and trips YouTube's
  inauthentic-content enforcement (spec §12).

## 2. Description standard
- **Research-led, BEFORE writing.** The agent researches what attracts and ranks in the channel's
  niche *before* composing a description, drawing on **both**:
  - **YouTube's own signals** (Data/Analytics API): the search terms bringing viewers in, and what is
    performing on this channel and among comparable videos — *the mirror*.
  - **Broader web/trend research**: rising topics and phrasings not yet visible in the channel's own
    numbers — *the windshield*, so the agent writes toward where attention is heading, not only where
    it has been.
- **Rich and SEO-driven.** Written to attract new viewers and subscribers — strong, natural keyword
  coverage woven into genuinely engaging prose, never keyword-stuffed. This is a growth/revenue task
  and is treated with that seriousness.
- **Length decided by research, not fixed.** The agent chooses length and shape from what performs for
  the niche and topic — not a hardcoded template. Later evidence tunes that judgement (§4).
- **Structure** (a shared skeleton; the *voice* is per-channel): an engaging, keyword-aware opening
  that earns the click and the watch → timestamped chapters where the content supports them → a
  single, graceful **one-line** AI/synthetic-content disclosure at the very **bottom**.
- **Per-channel voice.** The skeleton is shared; the voice is drawn from each channel's onboarding
  config (a wildlife documentary, a kids' channel, and a financial-news channel read nothing alike).
  The lion film is the calibration reference for the wildlife voice.
- **Disclosure wording.** Human-readable and unobtrusive — a single line at the foot, e.g. *"Narration
  and score are AI-assisted; all footage is licensed stock."* Accurate, graceful, never a form-filled
  label at the top. (YouTube's synthetic-content flag is still set programmatically regardless — this
  is only the human-facing text.)

## 3. Separation of public text and internal record
The lion-upload leak (`…-footage-manifest.md` in the public description) happened because the agent
reused internal metadata as public text. Structural fix: the description generator composes **public
text only**; the provenance/audit trail (manifest reference, asset IDs, QC numbers, job/video IDs) is
written to the **internal record** (events/DB) and is never emitted into any public field. Two
outputs, two destinations, no overlap.

## 4. The metadata performance loop (specified now, ACTIVATED when public)
- **Principle.** Descriptions, titles, and tags are **not fixed**. Once a video is public, the agent
  measures how its metadata actually performs and adapts — future videos are written better, and
  existing metadata can be revised on evidence.
- **Metrics tracked per video, once public:** impressions, click-through rate (CTR), views, average
  view duration, subscribers gained, and the search/traffic-source terms bringing viewers in.
  (Impressions + CTR are the sharpest signal that a title/description is or isn't earning clicks.)
- **Attribution and adaptation.** Correlate metadata attributes (keywords, length, phrasing,
  structure) with these outcomes per channel; feed the learning back so the generator improves over
  time, and flag underperforming metadata on existing videos for revision.
- **HONEST CONSTRAINT — this switches on with public data.** A private or zero-view upload yields
  nothing to learn from. The loop is real only once videos are public and enough data has accumulated
  (typically days to weeks). It must **never fabricate performance signals or "adapt" on absent data**
  — with no data it says so and writes from research (§2) alone.
- **Layer-1 obligation (build now so the loop has something to read later).** Even before the loop is
  active, the metadata pipeline must (a) store each published video's initial description/title/tags
  with a version and timestamp, and (b) reserve the fields the loop will populate (the metrics above,
  keyed by video and period) — mirroring how the cost/revenue ledgers were laid down before their
  features existed. When analytics come online, the history is already captured.

## 5. Dependencies & phasing
- Research-led writing (§2) and the performance loop (§4) both depend on the YouTube Analytics/Data
  access (now unlocked via OAuth) and on the competitor & trend-analysis capability (spec §14.5).
- **Layer 1 (now, testable now):** the doctrine (§1) and the research-led description standard
  (§2–§3), proven against the lion film's regenerated description.
- **Layer 2 (specified now, activated later):** the performance loop (§4) — its data foundations laid
  now, switched on across the analytics/learning slices (Slice 6 / Phase 2) when videos are public.
  Nothing in the loop runs on zero-view data.

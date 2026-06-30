# Lion Documentary #01 — Footage Manifest & Provenance Log

**Status: RECONCILED against the locked film (`lion-doc-01_final.mp4` / `_ambience` / `_scored`),
2026-06-30.** This record now reflects the clips **actually used in the locked cut**, established from
the assembly inputs (`lion-doc-01-edit-plan.md` + the per-beat build scripts) and verified against the
real files in `assets/lion-doc-01/clips/` — not inferred from the original plan. The locked film uses
**17 unique source clips** (some reused across beats). See "What changed" at the bottom.

## Licensing (carry these)
- Pexels clips → **Pexels License**; Pixabay clip → **Pixabay Content License**. Both: free for
  commercial/YouTube use, **no attribution required**; raw clips not resold standalone (our edited
  doc is a new work, so we're clean).
- **No music from these sites** (Content ID risk). Music is original (ElevenLabs, see
  `assets/lion-doc-01/music/PROVENANCE.md`); ambience is a claim-safe field recording.
- The URL + contributor recorded per clip is our defence if a clip was ever mis-uploaded.

## How URLs were established (and the one caveat)
- **Logged (10 clips):** carried from the original manifest with their real source URLs.
- **`†` Derived (7 clips):** these were swapped in during selection and never logged. Their Pexels
  **asset ID is embedded in the original download filename** (`<id>_<w>_<h>_<fps>fps.mp4` is Pexels's
  naming), so the URL is **derived** from that ID as `https://www.pexels.com/video/<id>/` — derivation
  from authoritative data, **not** invention. Caveat: live verification was blocked — Pexels returns a
  blanket **HTTP 403** to programmatic requests (confirmed: the same 403 for a known-valid ID and a
  fake ID), so the format could not be HTTP-checked from this machine. The embedded ID is the asset's
  identifier and resolves in a browser. **No URL was fabricated.**
- Timestamps are each file's on-disk date (`stat`); all downloaded **2026-06-24**.
- Contributor left **"(see page)"** where not already logged — the URL resolves to it (lowest priority).

## USED IN THE LOCKED FILM (beat order, 17 unique clips)

| Beat | File on disk | Source | URL | License | Downloaded | Contributor | Logged? |
|---|---|---|---|---|---|---|---|
| 1 | `14301979_3840_2160_24fps.mp4` | Pexels | https://www.pexels.com/video/14301979/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 1 | `11906941_3840_2160_24fps.mp4` | Pexels | https://www.pexels.com/video/11906941/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 1 | `20316284-uhd_3840_2160_25fps.mp4` | Pexels | https://www.pexels.com/video/a-field-with-trees-and-grass-in-the-distance-20316284/ | Pexels License | 2026-06-24 | (see page) | logged (old #4) |
| 1 | `13309521_1080_1920_30fps.mp4` | Pexels | https://www.pexels.com/video/13309521/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 2 | `8476160-uhd_3840_2160_25fps.mp4` | Pexels | https://www.pexels.com/video/video-of-a-lion-8476160/ | Pexels License | 2026-06-24 | Nicky Pe | logged (old #7) |
| 2 | `300312.mp4` | Pixabay | https://pixabay.com/videos/lion-nature-animal-predator-mane-300312/ | Pixabay Content License | 2026-06-24 | (see page) | logged (old #18) |
| 2 | `15780896_2160_3840_30fps.mp4` | Pexels | https://www.pexels.com/video/15780896/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 3 | `16728725-uhd_3840_2160_30fps.mp4` | Pexels | https://www.pexels.com/video/lowe_lowin-16728725/ | Pexels License | 2026-06-24 | (see page) | logged (old #10) |
| 3 | `5607553-hd_1920_1080_24fps.mp4` | Pexels | https://www.pexels.com/video/a-lion-and-lioness-in-the-fields-5607553/ | Pexels License | 2026-06-24 | Zlatin Georgiev | logged (old #9) |
| 3 | `14813527_1080_1920_24fps.mp4` | Pexels | https://www.pexels.com/video/14813527/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 4 | `5607553-hd_1920_1080_24fps.mp4` | Pexels | *(reuse of Beat 3)* | Pexels License | 2026-06-24 | Zlatin Georgiev | logged (old #9/#12) |
| 4 | `853900-hd_1920_1080_25fps.mp4` | Pexels | https://www.pexels.com/video/lions-at-the-wild-853900/ | Pexels License | 2026-06-24 | Coverr | logged (old #13) |
| 5 | `9557810-hd_1920_1080_30fps.mp4` | Pexels | https://www.pexels.com/video/close-up-shot-of-a-lion-9557810/ | Pexels License | 2026-06-24 | Gal Shapira | logged (old #14) |
| 5 | `18553643-hd_1920_1080_24fps.mp4` | Pexels | https://www.pexels.com/video/lowenbabys-18553643/ | Pexels License | 2026-06-24 | (see page) | logged (old #15) |
| 6 | `7710516-hd_1920_1080_25fps.mp4` | Pexels | https://www.pexels.com/video/lion-standing-on-a-rock-7710516/ | Pexels License | 2026-06-24 | Mikhail Nilov | logged (old #17) |
| 6 | `16199982_3840_2160_30fps.mp4` | Pexels | https://www.pexels.com/video/16199982/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 6 | `20316284-uhd_3840_2160_25fps.mp4` | Pexels | *(reuse of Beat 1)* | Pexels License | 2026-06-24 | (see page) | logged (old #4) |
| 7 | `15452953_1920_1080_60fps.mp4` | Pexels | https://www.pexels.com/video/15452953/ † | Pexels License | 2026-06-24 | (see page) | **derived** |
| 7 | `853900-hd_1920_1080_25fps.mp4` | Pexels | *(reuse of Beat 4)* | Pexels License | 2026-06-24 | Coverr | logged (old #13) |
| 7 | `9222045-hd_1080_1920_30fps.mp4` | Pexels | https://www.pexels.com/video/a-golden-sunset-9222045/ | Pexels License | 2026-06-24 | (see page) | logged (old #19) |

Per-beat notes: B1 cold open (aerial → dry grass → tree-dotted plain → lion walks in); B2 at rest
(close-up → mane → regal); B3 the pride; B4 the hunt; B5 the cubs; B6 the roar (`16199982` is the
roar shot — its own audio is silent; the roar SFX is separate); B7 golden-hour close. `13309521`,
`15780896`, `14813527`, `9222045` are vertical clips used center-cropped to 16:9.

## NEEDS RECOVERY
**None.** Every clip in the locked film has an established URL — 10 logged, 7 derived from the
embedded Pexels asset ID. Nothing in the final cut is missing a URL.

## NOT USED (present on disk or in the old plan, but not in the locked film)
- `9448995-uhd_3840_2160_30fps.mp4` — giraffes (old #2). On disk, **unused** (cut at script stage).
- `13025095_1080_1920_24fps.mp4` — distant male lion. Reserve; was in the **rejected Beat 4 v1** and
  swapped out. **Unused.** (ID-derived ref for the record: https://www.pexels.com/video/13025095/ †)
- `13309521_1080_1920_30fps copy.mp4` — exact **duplicate** of the Beat 1 lion clip. Unused (dedup).
- Old-manifest clips never used in the cut: `#1` giraffe 25753512 (also not on disk), `#3` aerial
  33660366, `#5` sunrise 36441545, `#6` lion-walking 31150342, `#8` resting 37251364, `#11` lioness
  34970161, `#16` roar 38156859, `#20` strolling 30393112. These were planned but replaced during
  selection; their original URLs remain valid Pexels pages but are not part of this film.

## What changed vs. the old manifest
- The old manifest listed **20 planned clips**; the locked film actually uses **17**, of which only
  **10** were in the old manifest. **7 clips were swapped in during selection and never logged** —
  now added with **ID-derived** Pexels URLs (marked †).
- **9 old-manifest clips are not in the film** (both giraffes, plus the original aerial, sunrise,
  lion-walking, resting, lioness, roar, and strolling selections) — they were replaced.
- "Suggested filenames" replaced with **actual on-disk filenames** (ground truth).
- **NEEDS RECOVERY is empty** — all URLs established without fabricating any.

# Lion Documentary #01 — Edit Plan & Clip→Beat Mapping

Working document produced from visual inspection of the 20 downloaded clips (frames extracted
mid-clip and identified). This is the assembly reference. **Not the manifest** — the on-disk files
differ from `lion-doc-01-footage-manifest.md` (see "Reconciliation" below).

Target output: **1920×1080 (1080p), 24 fps**, h.264 + AAC. Most strong footage is landscape
1080p/4K; output 1080p is the safe common denominator.

## Full clip inventory (as identified on disk)

| File (on disk) | Res | Orient | Dur | Embedded audio | Content (identified from frame) |
|---|---|---|---|---|---|
| 14301979_3840_2160_24fps | 4K | land | 14.2s | none | Aerial savanna, wide plains + trees |
| 20316284-uhd_3840_2160_25fps | 4K | land | 7.6s | none | Savanna landscape, scattered trees, dusk haze |
| 11906941_3840_2160_24fps | 4K | land | 11.8s | none | Dry grass / wildflowers close-up, green bokeh |
| 15452953_1920_1080_60fps | 1080 | land | 45.0s | silent | Aerial golden sun over waterhole, reflection |
| 13025095_1080_1920_24fps | 1080 | **PORT** | 18.9s | none | Lion walking toward camera, distant, big sky |
| 13309521_1080_1920_30fps | 1080 | **PORT** | 13.2s | none | Male lion walking toward camera, close, mane |
| 8476160-uhd_3840_2160_25fps | 4K | land | 20.8s | silent | Male lion close-up portrait, at rest, sandy ground |
| 300312 (Pixabay) | 4K | land | 14.1s | none | Male lion resting in profile, mane lit |
| 15780896_2160_3840_30fps | 4K | **PORT** | 21.1s | none | Male lion resting under tree, regal |
| 5607553-hd_1920_1080_24fps | 1080 | land | 27.7s | none | Lioness walking in green field |
| 16728725-uhd_3840_2160_30fps | 4K | land | 25.7s | silent | Lion + lioness, male nuzzling/grooming her (social pair) |
| 14813527_1080_1920_24fps | 1080 | **PORT** | 47.0s | none | Lioness lying in tall grass, back to camera |
| 853900-hd_1920_1080_25fps | 1080 | land | 13.5s | none | Two lions roaming, distant, wide savanna |
| 9557810-hd_1920_1080_30fps | 1080 | land | 52.1s | **real audio** | Lion cub on a rock, close-up |
| 18553643-hd_1920_1080_24fps | 1080 | land | 53.9s | silent | Three cubs on a log, adult lion behind |
| 7710516-hd_1920_1080_25fps | 1080 | land | 21.1s | silent | Male lion standing on a rock, green bg |
| 16199982_3840_2160_30fps | 4K | land | 9.7s | **none** | Male lion **ROARING**, head up, mouth open |
| 9222045_1080_1920_30fps | 1080 | **PORT** | 14.8s | real audio | Golden sunset, sun flare, backlit grass |
| 9448995-uhd_3840_2160_30fps | 4K | land | 97.3s | real audio | **GIRAFFES** — UNUSED per script note |
| 13309521..._30fps **copy** | — | — | 13.2s | — | **Exact duplicate of 13309521 — DROP** |

## Proposed clip → beat mapping (landscape-first)

All beats use landscape clips except the cold-open lion entrance (see flag B).

- **Beat 1 — Cold open (~70s):** `14301979` aerial savanna → `11906941` dry-grass detail →
  `20316284` tree-dotted plain → `15452953` golden sun over water → **lion entrance** (see flag B).
- **Beat 2 — At rest (~75s):** `8476160` close-up at rest → `300312` profile, mane lit.
- **Beat 3 — The pride (~100s):** `5607553` lioness walking → `16728725` lion+lioness nuzzling (pair).
- **Beat 4 — The hunt (~100s):** `853900` two lions roaming → `5607553` (different cut, lioness moving low).
- **Beat 5 — Cubs (~75s):** `9557810` cub on rock → `18553643` cubs on log with adult.
- **Beat 6 — The roar (~60s):** `7710516` standing on rock → `300312`/`15780896` mane portrait (reuse) →
  `16199982` the roar. **Roar audio: see flag A.**
- **Beat 7 — Golden-hour close (~60s):** strolling lion (see flag C) → `15452953` or `9222045` sunset.

Unused: `9448995` (giraffes), `13309521 copy` (dup). Portrait clips held in reserve.

## Reconciliation vs. manifest
The downloaded set is **not** the manifest's 20. IDs that match the manifest: 20316284 (#4),
8476160 (#7), 5607553 (#9), 16728725 (#10), 853900 (#13), 9557810 (#14), 18553643 (#15),
7710516 (#17), 300312 (#18), 9222045 (#19), 9448995 (#2, unused giraffe). IDs **not in the
manifest** (newer/substituted downloads): 14301979, 11906941, 15452953, 13025095, 13309521,
15780896, 14813527, 16199982. Several manifest clips were apparently replaced — notably the
manifest's roar (#16 = 38156859) is now `16199982`, and new aerials/landscapes were added. The
provenance for the 8 unlisted clips is not logged; **recommend Banks adds their Pexels/Pixabay URLs
to the manifest** to keep the audit trail complete (project provenance rule).

## Flags / decisions needed
- **A — Beat 6 roar audio (blocking the roar moment):** the roaring clip `16199982` has **no audio
  stream**, and no other clip carries a real roar (standing-on-rock and the pair are digital silence
  at −91 dB; only the cub clip has real audio, possibly music). So "roar natural sound up" cannot
  come from the footage. Options: (1) Banks sources ONE claim-safe natural roar (CC0/public-domain,
  with provenance — a nature SFX, not music); (2) carry Beat 6 on narration + a low swell in the
  ambient bed, no literal roar; (3) skip. Recommend (1) or (2).
- **B — Cold-open lion entrance is portrait-only:** the only "lion walking toward camera" clips
  (`13025095`, `13309521`) are vertical. For a 16:9 film I'd center-crop `13309521` (tight walking
  shot, loses sky/foreground) with a slow push. Acceptable but a compromise — flagging it.
- **C — Beat 7 "strolling lion in golden light" not on disk as landscape:** no clear golden-hour
  strolling-lion landscape clip. Plan to close on `5607553`/`853900` (lions in field) into the
  `15452953` sunset, or center-crop portrait `9222045`. Minor.
- **Embedded clip audio:** stripped by default (claim-proof). The cub clip's real audio may be
  music — not used.

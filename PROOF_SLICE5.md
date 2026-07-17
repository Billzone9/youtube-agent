# Slice 5 — live proof output

The agent wrote both pieces below **itself**, via the direct Claude API behind the swappable provider
layer. Sonnet (`claude-sonnet-4-6`) for prose, Haiku for tags/labels. Research was honestly
unavailable (`research_available=False`) — it wrote from niche knowledge and did not claim otherwise.
Run on the Mac only; no YouTube, no publishing, no VPS.

- **Actual cost this run: £0.0400** (description £0.0100 + script £0.0300). Month-to-date £14.63 / £200 (m1), remaining £185.37.
- Both outputs passed the AI-tell scanner (`flagged=False`) on the first attempt — no regenerations needed.
- The lion description passed the internal-artifact guard (CLEAN) and was stored as an authored
  `video_metadata` v3 (`source='research_writer'`, **not** applied — truthful, not live).

---

## (a) Autonomous lion description vs the locked hand-authored reference

**AGENT'S OWN TITLE:**   `Lion — Lord of the Savanna | A Cinematic Wildlife Documentary`
**REFERENCE TITLE:**     `Lion — Lord of the Savanna`

### AGENT'S OWN DESCRIPTION

> The lion owns the African savanna in a way no other creature quite manages. This cinematic portrait follows one pride through a single day on the open plains — from the long, drowsy sprawl of the midday heat, through the patient, unhurried discipline of the evening hunt, to the roar that moves across the grassland like a slow tide as darkness settles in.
>
> This is not a film built on urgency. It lingers: on the lioness who carries the weight of the pride's survival, on the cubs discovering their own small authority in the dust, on the moment before the charge when everything goes still. The savanna has its own rhythm, and the lion has learned every beat of it. Watch with the sound up.
>
> Chapters:
> 0:00 The kingdom waits
> 0:51 The weight of rest
> 1:54 The pride's covenant
> 2:58 The patient hunt
> 3:59 Learning to kill
> 5:03 The roar across the plain
> 5:47 The savanna's dusk
>
> Narration and score are AI-assisted; all footage is licensed stock.

### REFERENCE DESCRIPTION (locked, hand-authored, for comparison)

> The lion rules the African savanna without rival. Under a sky that turns from gold to fire, this short wildlife documentary follows one pride across a single unhurried day on the plains — the drowsy heat of noon, the patient discipline of the hunt, the tumble of cubs learning their place, and the roar that rolls across the grasslands as the light fails.
>
> It is filmed as a calm, cinematic portrait rather than a chase, lingering on the small truths of lion life: the bonds that hold a pride together, the weight a lioness carries for them all, and the quiet authority of the animal we have long called the king of beasts. Settle in, turn the sound up, and let the savanna close in around you.
>
> Chapters:
> 0:00 The kingdom and its sovereign
> 0:51 The lion at rest
> 1:54 The pride
> 2:58 The hunt
> 3:59 The cubs
> 5:03 The roar
> 5:47 Golden-hour close
>
> Narration and score are AI-assisted; all footage is licensed stock.

### Tags

**AGENT'S TAGS:**   lion documentary, african savanna wildlife, lion pride documentary, cinematic nature documentary, wildlife documentary narrated, lion hunt footage, relaxing wildlife film, lion behavior documentary, savanna wildlife film, lion cubs nature documentary, calm nature documentary full, african wildlife narration, lion roar documentary, long form wildlife video, poetic nature documentary

**REFERENCE TAGS:**  lion, lion documentary, lion pride, african savanna, lion documentary narrated, lion documentary full, relaxing wildlife documentary, calm nature documentary, cinematic wildlife documentary, narrated wildlife documentary, african wildlife documentary, lions of the savanna, lion hunt documentary, savanna wildlife

### Scan results (agent output)
- **guard:** CLEAN ✅ (no internal artifacts)
- **AI-tell scan:** `flagged=False`  •  em-dash 0.6/100w  •  exclamations 0  •  tricolon (advisory) 0  •  lexical crutches (advisory) none
- **provenance:** provider=AnthropicProvider, model=claude-sonnet-4-6, style_spec_version=1, tells_thresholds_version=1, tells_flagged=False, research_available=False
- stored as authored `video_metadata` v3 (`research_writer`, not live)

---

## (b) Autonomous footage-led script — emperor penguin

A subject the agent has not seen (no lion vocabulary to recycle — proof it's the agent's own writing).
Judge against the lion script's voice: poetic surface, accurate underneath, no AI tells.

**TITLE:** `Emperor — Father of the Dark`
**Target** ~150s / ~270 words   •   **Actual VO:** 441 words, 4 beats

---

**BEAT 1 — Beat 1 — The last light   (~40s)**

**VISUALS (shot-brief):** Wide aerial or sweeping ground-level shot of Antarctic ice shelf stretching to horizon under a dimming sky — last trace of sun at the edge of the world. Then a slow pan across hundreds of emperor penguins standing motionless on the ice, the colony vast and dark against white.

**VO:**
> At the bottom of the world, the sun makes its decision.
>
> *(beat)*
> Slowly — over days, not hours — it flattens against the horizon and withdraws. And when it goes, it does not come back. Not for two months. Not for longer.
>
> *(over the colony)*
> What remains stands here on the ice. Four, five, ten thousand birds. A city with no walls and no shelter, breathing the coldest air on earth. They have come to this place to do something almost impossible.
>
> They have come here to begin.

---

**BEAT 2 — Beat 2 — The egg and the father   (~38s)**

**VISUALS (shot-brief):** Close shot of a male emperor penguin looking down, shuffling feet. Cut to reveal a single large egg resting on top of his feet, tucked under a warm fold of belly skin — the brood pouch. Slow zoom to the egg itself, then back to the father's face, still and watchful.

**VO:**
> A single egg.
>
> *(beat)*
> No nest. No burrow. No branch or grass or sheltering stone. Only the feet of its father, and the brood pouch above — a fold of warm skin, held against the body, holding just enough heat to keep what is inside alive.
>
> *(beat)*
> The female has already gone. She walked to the sea weeks ago to feed, leaving him with this one fragile thing to carry through the dark. He will not eat again for roughly two months. He will not set that egg down.
>
> Not once.

---

**BEAT 3 — Beat 3 — The huddle   (~45s)**

**VISUALS (shot-brief):** Wide shot of the famous emperor penguin huddle — a dense, slow-shifting mass of birds pressed together, seen from above if possible, or from ground level showing the wall of bodies. Time-lapse or slow pan showing the huddle rotating — birds on the outer edge shuffling inward, those at the centre drifting out. Wind and driven snow visible against dark sky.

**VO:**
> The blizzard arrives — as it always does — without warning.
>
> Winds that can reach two hundred kilometres an hour. Temperatures that fall past minus sixty degrees Celsius with the wind chill. Nothing alive, anywhere on this continent, is built for this. Except for what happens next.
>
> *(over the huddle)*
> They press together. Shoulder to shoulder, foot to foot — a single breathing mass of ten thousand birds, sharing the only warmth there is. At the centre, the temperature climbs to thirty-seven degrees. But no bird stays at the centre. The huddle rotates, slowly, constantly — each penguin cycling inward from the frozen edge to the warmth, then outward again, so that every father takes his turn in the cold and every father takes his turn in the heat.
>
> *(beat)*
> Not one of them decided this. It simply is.

---

**BEAT 4 — Beat 4 — The return of the light   (~42s)**

**VISUALS (shot-brief):** A thin line of pale gold appearing at the horizon — first light returning after the polar winter. Male penguins, visibly thinner, still standing with eggs or now with small grey chicks just hatched, balanced on feet. A female emperor approaching across the ice, returning from sea. Close shot of a newly hatched chick peering out from under its father's brood pouch — tiny face, enormous world.

**VO:**
> And then — at the far edge of the darkness — light.
>
> *(beat)*
> The fathers have lost nearly half their body weight. They have stood here, in the coldest place on earth, for the length of an Antarctic winter. And most of them are still standing.
>
> *(over the returning females)*
> Across the ice come the females, heavy with food from the sea — each one navigating back to a colony of thousands, finding a single voice in that crowd: his. They have not seen each other since autumn.
>
> *(over the chick)*
> And here, beneath the brood pouch, blinking into its first light — the reason for all of it. Grey. Improbably small. Alive.
>
> *(beat)*
> The dark kept nothing it was given to keep.

---

### FACTS USED (accuracy block)
- [established] Emperor penguins breed during the Antarctic winter, in complete polar darkness lasting roughly two months
- [established] Male emperor penguins incubate a single egg balanced on their feet under a brood pouch
- [established] The female leaves after laying the egg and the male fasts for approximately two months (around 65 days) during incubation
- [established] Male emperors lose close to half their body weight during the incubation fast
- [established] Emperor penguin colonies huddle together for warmth; the huddle rotates so birds cycle between the cold outer edge and warm centre
- [established] Temperature at the centre of the huddle can reach approximately 37 degrees Celsius
- [established] Antarctic blizzard wind chill can bring effective temperatures to around minus 60 degrees Celsius
- [established] Wind speeds in Antarctic blizzards can reach around 200 km/h
- [established] Colony sizes for emperor penguins can reach into the thousands — large colonies number in the tens of thousands
- [established] Males and females recognise each other by individual vocalisations within the colony

### Scan results (script output)
- **AI-tell scan:** `flagged=False`  •  em-dash 2.49/100w  •  exclamations 0  •  not_only_but_also 0  •  tricolon (advisory) 0  •  lexical crutches (advisory) none
- **provenance:** provider=AnthropicProvider, model=claude-sonnet-4-6, style_spec_version=1, tells_thresholds_version=1, tells_flagged=False, research_available=False

---

## Cost

```
THIS RUN cost: £0.0400  (description £0.0100 + script £0.0300)
Month-to-date spend: £14.63 / £200 (m1)  •  remaining £185.37
```

Written to `cost_ledger` (category `ai_generation`, per-call, idempotent on the Anthropic request id).

---

## Honest observations (for your judgement)

- **AI-tell result is the headline:** both pieces passed on the first try. The penguin script's em-dash
  density (2.49/100w) sits right on the lion narration's own baseline (2.50/100w) — the writer landed
  the house cadence without being told a number, and used zero exclamation marks and no generic openers.
- **Script overran the length target:** 441 words against a ~270 target (and beats sum to ~165s vs the
  150s target). The prose is strong, but the writer treated the word/runtime target loosely. Easily
  tightened by hardening the target in the prompt / trimming in a pass — flagging it rather than hiding it.
- **Cosmetic label duplication:** the script beat headers read "Beat 1 — Beat 1 — …" because the model
  included "Beat 1 —" inside the label it returned and the printer also prefixes "BEAT 1 —". A one-line
  fix (strip a leading "Beat N —" from returned labels, or don't prefix). No effect on the VO or facts.
- **Actual £0.04 vs the £0.027 estimate:** within range; the difference is mostly the script running
  longer (more output tokens) than the 270-word assumption.
- **Chapter labels** for the lion were authored by the agent over the real cut timestamps (it did not
  invent timestamps) — e.g. "The pride's covenant", "Learning to kill", "The savanna's dusk".

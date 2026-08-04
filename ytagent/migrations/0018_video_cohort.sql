-- M1 item 1 — the cohort marker for the Shorts-discovery experiment. The 8-week success criterion
-- compares Shorts impressions vs long-form impressions (PLAN_M1_SHORTS), so both sides need a label the
-- retrospective YouTube-Analytics pull can group by. Free text (experiment labels, not a fixed enum):
-- 'm1-shorts' | 'm1-longform'. produce_short/produce_video set it at submit; the pull filters by date window.
ALTER TABLE videos ADD COLUMN IF NOT EXISTS cohort text;

-- BACKFILL the two ALREADY-PUBLISHED long-forms as the baseline the Shorts get compared against — without
-- this the comparison has no long-form side (they were published 2026-08-02, before this column existed).
UPDATE videos SET cohort = 'm1-longform'
 WHERE youtube_video_id IN ('yGdNuUB5f_I', 'EY9DhJdnt_w') AND cohort IS NULL;

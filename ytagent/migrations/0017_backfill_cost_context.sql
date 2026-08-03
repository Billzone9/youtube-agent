-- B3 item 4 — backfill metadata.context on legacy untagged ai_generation rows, so honest ROI can
-- separate production from calibration. NOT a blanket classification (Banks): attribute what belongs
-- to a film, tag only the genuinely untraceable remainder.
--
-- Three precise buckets, applied in order (idempotent — each touches only rows still context-null):
--   1. Job-linked ai_generation spend  -> 'production'  (real produce/remake/curate jobs: the wolf
--      28/29/34/41, the elephant 99/155/276 — a failed film is still production spend, not calibration).
--   2. The lion's score (reconciled ElevenLabs Music, no job_id, description 'Lion film...') -> 'production'
--      + film tag; the lion was hand-built (Phase 1.1) so it carries no produce job.
--   3. Everything else with no job_id (dev/test music+TTS+LLM) -> 'calibration' (genuinely untraceable).

-- 1. job-linked -> production
UPDATE cost_ledger
   SET metadata = metadata || '{"context":"production"}'::jsonb
 WHERE category = 'ai_generation'
   AND job_id IS NOT NULL
   AND (metadata->>'context') IS NULL;

-- 2. the lion score (no job_id) -> production, attributed to the hand-built lion film
UPDATE cost_ledger
   SET metadata = metadata || '{"context":"production","film":"lion-doc-01"}'::jsonb
 WHERE provider = 'ElevenLabs Music'
   AND job_id IS NULL
   AND description LIKE 'Lion film%'
   AND (metadata->>'context') IS NULL;

-- 3. remaining untraceable no-job ai_generation -> calibration
UPDATE cost_ledger
   SET metadata = metadata || '{"context":"calibration"}'::jsonb
 WHERE category = 'ai_generation'
   AND job_id IS NULL
   AND (metadata->>'context') IS NULL;

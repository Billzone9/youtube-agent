-- Slice 3 — assembly job lifecycle.
-- The jobs.status CHECK had no terminal for a "produce an artifact" (non-publish) job. Add
-- 'assembling' (rendering in progress) and 'assembled' (artifact ready, awaiting description +
-- approval). Additive only — mirrors how 0002 extended videos.status.

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
  CHECK (status IN ('queued','running','awaiting_approval','approved','rejected',
                    'published','published_dryrun','assembling','assembled','failed','cancelled'));

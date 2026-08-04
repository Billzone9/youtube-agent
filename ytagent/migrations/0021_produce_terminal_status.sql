-- D2 (2026-08-04) — a produce job needs a clean TERMINAL status. Before this, a produce job that
-- successfully assembled + submitted its video rested at 'assembled' forever (never terminal), so it was
-- indistinguishable from a job still mid-assembly and "stuck at assembling" queries were unreliable.
-- Add 'produced' (terminal: the artifact was built and submitted for approval; the produce job's work is
-- done — the publish job + approval carry it forward). In-progress stays 'assembling' (resumable);
-- 'produced' is never resumed.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
  CHECK (status IN ('queued','running','awaiting_approval','approved','rejected',
                    'published','published_dryrun','assembling','assembled','produced','failed','cancelled'));

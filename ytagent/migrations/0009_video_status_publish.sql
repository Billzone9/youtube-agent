-- The publish slice adds two video states the original check omits:
--   'publishing' — a publish_public (videos.update to public) is in flight (parallels 'uploading').
--   'misplaced'  — Amendment A: an upload landed on the WRONG channel; recorded, never 'published',
--                  and surfaced for manual deletion. A distinct terminal state, not 'failed'.
-- Idempotent: drop the old check and recreate the widened one.

ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_status_check;
ALTER TABLE videos ADD CONSTRAINT videos_status_check CHECK (
  status = ANY (ARRAY[
    'draft','awaiting_approval','approved','uploading','publishing',
    'rejected','published','published_dryrun','failed','misplaced'
  ])
);

-- The gated publish-to-public applies the clean description via a videos.UPDATE, recorded as
-- applied_via='update_publish' (distinct from 'upload_insert' = set at upload, 'studio_manual' = pasted
-- by hand, 'api_update' = a generic API edit). Widen the check to admit it. Idempotent.

ALTER TABLE video_metadata DROP CONSTRAINT IF EXISTS video_metadata_applied_via_check;
ALTER TABLE video_metadata ADD CONSTRAINT video_metadata_applied_via_check CHECK (
  applied_via = ANY (ARRAY['upload_insert','studio_manual','api_update','update_publish'])
);

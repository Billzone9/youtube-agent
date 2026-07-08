-- Slice 2 — real publishing.
-- 1) videos.status gains 'uploading' (during a live upload) and 'failed'.
-- 2) Channel identity: the wildlife row becomes Banks's real channel (one-shot data fix here,
--    NOT in seed — seed runs on every startup and would clobber future dashboard edits).
-- 3) A live YouTube video id is unique.

ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_status_check;
ALTER TABLE videos ADD CONSTRAINT videos_status_check
  CHECK (status IN ('draft','awaiting_approval','approved','uploading','rejected',
                    'published','published_dryrun','failed'));

UPDATE channels
   SET name = 'The Tales of Wildlife and Nature',
       config = jsonb_set(config, '{youtube_handle}', '"@TheTalesofWildlifeandNature"')
 WHERE slug = 'wildlife' AND name = 'Wildlife & Nature';

CREATE UNIQUE INDEX IF NOT EXISTS videos_youtube_id_key
  ON videos (youtube_video_id) WHERE youtube_video_id IS NOT NULL;

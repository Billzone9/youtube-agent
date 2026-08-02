-- Channel identity (item 1 + Amendment A). An upload lands on whatever channel the OAuth token is
-- bound to (videos.insert has no channelId parameter), so channel safety must be VERIFIED, not assumed.
-- Record the wildlife channel's real YouTube channel id (read from the actual upload responses of the
-- lion yGdNuUB5f_I and elephant EY9DhJdnt_w — both landed here). The publisher asserts the insert/update
-- response's snippet.channelId equals this value; a mismatch records the video MISPLACED and alerts.
-- Only when absent, so a later dashboard edit is never clobbered (mirrors 0006's voice_profile backfill).

UPDATE channels
   SET config = jsonb_set(config, '{youtube_channel_id}', '"UCRkrZa2yjLLw-f67H2pYI2g"')
 WHERE slug = 'wildlife'
   AND config ->> 'youtube_channel_id' IS NULL;

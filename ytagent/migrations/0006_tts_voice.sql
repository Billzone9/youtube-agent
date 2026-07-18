-- E2E production — TTS voice config. seed.py inserts the channel ON CONFLICT DO NOTHING, so the
-- existing wildlife row never gains new voice_profile fields; patch it here (mirrors 0002's
-- youtube_handle backfill). Only when absent, so a later dashboard edit is never clobbered.

UPDATE channels
   SET config = jsonb_set(
                  jsonb_set(config, '{voice_profile,voice_id}', '"jvcMcno3QtjOzGtfpjoI"'),
                  '{voice_profile,model}', '"eleven_multilingual_v2"')
 WHERE slug = 'wildlife'
   AND config -> 'voice_profile' ->> 'voice_id' IS NULL;

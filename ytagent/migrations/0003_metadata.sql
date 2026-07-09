-- Layer 1 — public-facing description standard: data foundation.
-- Same conventions as 0001/0002: bigint PK for joins + public_id uuid for external ids;
-- timestamptz everywhere; text+CHECK for enums (not PG enum types); jsonb for structured data;
-- idempotency_key as a plain (non-partial) unique index so ON CONFLICT can infer it.
--
-- Two tables + one column:
--  * video_metadata — the AUTHORED public text (title/description/tags), versioned per video per
--    language. This is the single source of truth for what an audience sees; the leak is closed by
--    routing the publish path through here instead of hardcoded artifact strings.
--  * video_metrics  — RESERVED for Layer 2 (the performance loop). Empty now; the fields exist so
--    that when analytics read-scope lands, the history has somewhere to go (the ledger-before-the-
--    feature move). Never populated on private / zero-view uploads.
--  * videos.tags    — authored per-video SEO tags mirrored onto the video row (title/description
--    already live there); the publish body prefers these over the channel's default_tags.

-- ---------------------------------------------------------------------------
-- videos.tags — authored per-video tags (research-led SEO), mirrored like title/description.
-- ---------------------------------------------------------------------------
ALTER TABLE videos ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- video_metadata — versioned authored public text.
-- "Latest authored" = MAX(version).  "Currently live" = the row with the newest applied_at.
-- They differ deliberately: the lion's clean regen can be the latest authored version while the
-- old (leaked) text is still what YouTube is serving, because upload-only scope cannot update it.
-- ---------------------------------------------------------------------------
CREATE TABLE video_metadata (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id       uuid NOT NULL DEFAULT gen_random_uuid(),
  video_id        bigint NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  channel_id      bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  language        text NOT NULL DEFAULT 'en',       -- reserved for MLA; uniqueness spans it now
  version         integer NOT NULL,                 -- 1,2,3… per (video_id, language)
  title           text NOT NULL,                    -- PUBLIC
  description     text NOT NULL,                    -- PUBLIC
  tags            jsonb NOT NULL DEFAULT '[]'::jsonb,-- PUBLIC
  source          text NOT NULL DEFAULT 'manual'
                    CHECK (source IN ('legacy_artifact','layer1_manual','research_writer',
                                      'layer2_revision','manual')),
  research_notes  jsonb NOT NULL DEFAULT '{}'::jsonb, -- INTERNAL: the research that produced this
  generated_at    timestamptz NOT NULL DEFAULT now(),
  applied_at      timestamptz,                       -- when this version became live (NULL = never)
  applied_via     text CHECK (applied_via IN ('upload_insert','studio_manual','api_update')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX video_metadata_public_id_key ON video_metadata (public_id);
CREATE UNIQUE INDEX video_metadata_version_key   ON video_metadata (video_id, language, version);
CREATE INDEX video_metadata_video_id_idx ON video_metadata (video_id);
CREATE INDEX video_metadata_channel_id_idx ON video_metadata (channel_id);
CREATE INDEX video_metadata_applied_idx ON video_metadata (video_id, applied_at);
CREATE TRIGGER video_metadata_set_updated_at BEFORE UPDATE ON video_metadata
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- video_metrics — RESERVED for Layer 2. Fields the performance loop will populate, keyed by
-- video + period. period_start + grain (NOT a hardcoded month): day-grain YouTube data cannot be
-- back-filled, so we can roll day->month but never month->day. metadata_version_id makes Layer-2
-- attribution ("which authored text earned these numbers") a join, not a guess.
-- ---------------------------------------------------------------------------
CREATE TABLE video_metrics (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id            uuid NOT NULL DEFAULT gen_random_uuid(),
  video_id             bigint NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  channel_id           bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  metadata_version_id  bigint REFERENCES video_metadata(id) ON DELETE SET NULL,
  period_start         date NOT NULL,
  grain                text NOT NULL DEFAULT 'day'
                         CHECK (grain IN ('day','week','month','lifetime')),
  impressions          bigint,
  ctr                  numeric,          -- as reported by the API (not reconstructed)
  views                bigint,
  avg_view_duration_s  numeric,
  watch_time_minutes   numeric,
  subscribers_gained   integer,          -- net; may be negative
  search_terms         jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{term, views, impressions}]
  traffic_sources      jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{source, views, impressions}]
  source               text NOT NULL DEFAULT 'youtube_analytics'
                         CHECK (source IN ('youtube_analytics','manual','integration')),
  idempotency_key      text,             -- e.g. "yGdNuUB5f_I:day:2026-07-10"; re-pull upserts
  created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX video_metrics_public_id_key ON video_metrics (public_id);
CREATE UNIQUE INDEX video_metrics_idem_key ON video_metrics (idempotency_key);
CREATE INDEX video_metrics_video_period_idx ON video_metrics (video_id, period_start);
CREATE INDEX video_metrics_channel_period_idx ON video_metrics (channel_id, period_start);

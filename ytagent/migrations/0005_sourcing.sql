-- Slice 4 — asset sourcing. The provenance/cache record for every downloaded stock asset.
-- Conventions mirror 0001/0003: bigint identity PK + public_id uuid; timestamptz; text+CHECK enums;
-- jsonb for structured data; plain-unique idempotency_key (NULLs distinct) so ON CONFLICT can infer
-- it; set_updated_at trigger. Keyed by channel (channel-general). Cache key = source:asset_id.

CREATE TABLE sourced_assets (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id         uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id        bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  job_id            bigint REFERENCES jobs(id) ON DELETE SET NULL,   -- the run that first sourced it
  source            text NOT NULL CHECK (source IN ('pexels','pixabay')),
  asset_id          text NOT NULL,
  url               text NOT NULL,                    -- authoritative page URL (never fabricated)
  contributor       text,                             -- '(see page)' when absent
  licence           text NOT NULL,
  provenance_source text NOT NULL DEFAULT 'logged'
                      CHECK (provenance_source IN ('logged','derived')),
  local_path        text NOT NULL,
  width             integer,
  height            integer,
  duration_s        numeric,
  fps               numeric,
  orientation       text CHECK (orientation IN ('landscape','portrait','square')),
  title             text,
  tags              jsonb NOT NULL DEFAULT '[]'::jsonb,
  size_bytes        bigint,
  checksum          text,                             -- sha256, mirrors videos
  gate_pass         boolean NOT NULL DEFAULT false,
  gate_report       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- probe + noise checks
  shot_brief_ref    text,                             -- e.g. 'penguin:beat3'
  query_used        text,
  api_response      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- verbatim record → provenance recovery
  idempotency_key   text,                             -- 'source:asset_id'
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX sourced_assets_public_id_key ON sourced_assets (public_id);
CREATE UNIQUE INDEX sourced_assets_idem_key      ON sourced_assets (idempotency_key);
CREATE INDEX sourced_assets_channel_idx      ON sourced_assets (channel_id);
CREATE INDEX sourced_assets_source_asset_idx ON sourced_assets (source, asset_id);
CREATE TRIGGER sourced_assets_set_updated_at BEFORE UPDATE ON sourced_assets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

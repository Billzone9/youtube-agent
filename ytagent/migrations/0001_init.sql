-- Slice 1 — Spine + Gate. Channel-general, dashboard-ready schema.
-- Conventions: bigint PK for joins + public_id uuid for external/dashboard ids;
-- timestamptz everywhere; money is numeric(12,2) never float; text+CHECK for enums
-- (not PG enum types, so values evolve in a trivial migration); jsonb for editable config.
-- gen_random_uuid() is core in PostgreSQL 13+ (no extension needed).

-- ---------------------------------------------------------------------------
-- updated_at trigger helper
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- platform_settings — global, single-row-per-key config (e.g. budget ceiling)
-- ---------------------------------------------------------------------------
CREATE TABLE platform_settings (
  key         text PRIMARY KEY,
  value       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- channels — the registry. All per-channel config lives in config jsonb (no-code seam).
-- ---------------------------------------------------------------------------
CREATE TABLE channels (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id   uuid NOT NULL DEFAULT gen_random_uuid(),
  slug        text NOT NULL,
  name        text NOT NULL,
  status      text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived')),
  config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX channels_public_id_key ON channels (public_id);
CREATE UNIQUE INDEX channels_slug_key      ON channels (slug);
CREATE TRIGGER channels_set_updated_at BEFORE UPDATE ON channels
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- jobs — a unit of work for a channel.
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id   uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id  bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  type        text NOT NULL,
  status      text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','awaiting_approval','approved',
                                  'rejected','published','published_dryrun','failed','cancelled')),
  stage       text CHECK (stage IN ('research','script','assets','assemble','qc','publish')),
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- inputs
  result      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- outputs
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX jobs_public_id_key ON jobs (public_id);
CREATE INDEX jobs_channel_id_idx ON jobs (channel_id);
CREATE INDEX jobs_status_idx     ON jobs (status);
CREATE INDEX jobs_created_at_idx ON jobs (created_at);
CREATE TRIGGER jobs_set_updated_at BEFORE UPDATE ON jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- videos — a finished content artifact + its QC metadata.
-- ---------------------------------------------------------------------------
CREATE TABLE videos (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id        uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id       bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  job_id           bigint REFERENCES jobs(id) ON DELETE SET NULL,
  title            text NOT NULL,
  description      text,
  file_path        text NOT NULL,
  format           text NOT NULL DEFAULT '16:9' CHECK (format IN ('16:9','9:16')),
  duration_s       numeric,
  width            integer,
  height           integer,
  fps              numeric,
  loudness_lufs    numeric,
  peak_dbfs        numeric,
  noise_floor_db   numeric,
  size_bytes       bigint,
  checksum         text,          -- sha256
  provenance_ref   text,
  status           text NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','awaiting_approval','approved','rejected',
                                       'published','published_dryrun')),
  -- slice-2 columns (NULL under dry-run):
  youtube_video_id text,
  published_at     timestamptz,
  privacy_status   text,
  primary_language text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX videos_public_id_key ON videos (public_id);
CREATE INDEX videos_channel_id_idx ON videos (channel_id);
CREATE INDEX videos_job_id_idx     ON videos (job_id);
CREATE TRIGGER videos_set_updated_at BEFORE UPDATE ON videos
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- approvals — the human gate record (one per gated action).
-- ---------------------------------------------------------------------------
CREATE TABLE approvals (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id            uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id           bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  job_id               bigint NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
  kind                 text NOT NULL DEFAULT 'publish'
                         CHECK (kind IN ('publish','spend','social_post','community','promotion')),
  state                text NOT NULL DEFAULT 'pending'
                         CHECK (state IN ('pending','approved','rejected')),
  telegram_chat_id     text,
  telegram_message_id  bigint,
  callback_data        jsonb NOT NULL DEFAULT '{}'::jsonb,
  decided_by           text,
  reason               text,
  requested_at         timestamptz NOT NULL DEFAULT now(),
  decided_at           timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX approvals_public_id_key ON approvals (public_id);
CREATE INDEX approvals_pending_idx ON approvals (state) WHERE state = 'pending';
CREATE INDEX approvals_tg_msg_idx  ON approvals (telegram_message_id);
CREATE INDEX approvals_job_id_idx  ON approvals (job_id);
CREATE TRIGGER approvals_set_updated_at BEFORE UPDATE ON approvals
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- cost_ledger — every cost, keyed by channel (NULL = platform-wide fixed cost).
-- Currency seam: amount_original + currency + amount_gbp + fx_rate (conversion logic is later).
-- Governor semantics (no enforcement yet): committed = infrastructure+subscription; the rest is
-- discretionary/governed. promotion + campaign_id exist now so ROAS is later a query, not a migration.
-- ---------------------------------------------------------------------------
CREATE TABLE cost_ledger (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id        uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id       bigint REFERENCES channels(id) ON DELETE RESTRICT,
  job_id           bigint REFERENCES jobs(id) ON DELETE SET NULL,
  campaign_id      bigint,        -- reserved for ROAS; FK added with the promotion slice
  category         text NOT NULL
                     CHECK (category IN ('infrastructure','subscription','api_usage',
                                         'ai_generation','stock_media','promotion','other')),
  is_amortised     boolean NOT NULL DEFAULT false,
  provider         text,
  description      text,
  amount_original  numeric,
  currency         char(3) NOT NULL DEFAULT 'GBP',
  amount_gbp       numeric(12,2) NOT NULL,
  fx_rate          numeric,
  fx_rate_date     date,
  credits          numeric,
  incurred_at      timestamptz NOT NULL DEFAULT now(),
  period_month     date NOT NULL,    -- writer-set first-of-month, for monthly rollups
  reconciled       boolean NOT NULL DEFAULT false,
  idempotency_key  text,
  metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX cost_ledger_public_id_key ON cost_ledger (public_id);
-- plain unique (not partial): Postgres treats NULLs as distinct, and ON CONFLICT (idempotency_key)
-- can only infer a non-partial index.
CREATE UNIQUE INDEX cost_ledger_idem_key ON cost_ledger (idempotency_key);
CREATE INDEX cost_ledger_channel_month_idx ON cost_ledger (channel_id, period_month);
CREATE INDEX cost_ledger_category_idx ON cost_ledger (category);

-- ---------------------------------------------------------------------------
-- revenue_ledger — every revenue event, keyed by channel and stream. Empty in slice 1.
-- ---------------------------------------------------------------------------
CREATE TABLE revenue_ledger (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id        uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id       bigint NOT NULL REFERENCES channels(id) ON DELETE RESTRICT,
  campaign_id      bigint,        -- reserved for ROAS
  stream           text NOT NULL
                     CHECK (stream IN ('adsense','affiliate','sponsorship','product')),
  description      text,
  amount_original  numeric,
  currency         char(3) NOT NULL DEFAULT 'GBP',
  amount_gbp       numeric(12,2) NOT NULL,
  fx_rate          numeric,
  fx_rate_date     date,
  occurred_at      timestamptz NOT NULL DEFAULT now(),
  period_month     date NOT NULL,
  source           text NOT NULL DEFAULT 'manual'
                     CHECK (source IN ('manual','youtube_analytics','integration')),
  reconciled       boolean NOT NULL DEFAULT false,
  idempotency_key  text,
  metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX revenue_ledger_public_id_key ON revenue_ledger (public_id);
CREATE UNIQUE INDEX revenue_ledger_idem_key ON revenue_ledger (idempotency_key);
CREATE INDEX revenue_ledger_channel_month_idx ON revenue_ledger (channel_id, period_month);

-- ---------------------------------------------------------------------------
-- events — the audit timeline. Every state change appends here (single chokepoint in code).
-- Acid test: this table alone must reconstruct the whole story.
-- ---------------------------------------------------------------------------
CREATE TABLE events (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id    uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id   bigint REFERENCES channels(id) ON DELETE SET NULL,
  job_id       bigint REFERENCES jobs(id) ON DELETE SET NULL,
  approval_id  bigint REFERENCES approvals(id) ON DELETE SET NULL,
  type         text NOT NULL,
  message      text,
  data         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_channel_created_idx ON events (channel_id, created_at);
CREATE INDEX events_job_id_idx ON events (job_id);
CREATE INDEX events_type_idx ON events (type);

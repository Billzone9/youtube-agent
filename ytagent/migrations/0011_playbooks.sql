-- Slice 6a — the PLAYBOOK: the per-channel scheduling policy, stored as DATA (never code). One row per
-- channel. The scheduler reads this to decide what/when/how to produce; Banks edits it (dashboard/
-- Telegram later) to steer without a code change. Cadence/approval also live in channels.config; the
-- playbook is the *schedulable* policy and references the channel for voice/tone/approval.

CREATE TABLE playbooks (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id             uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id            bigint NOT NULL REFERENCES channels(id),
  enabled               boolean NOT NULL DEFAULT false,
  cadence               jsonb NOT NULL DEFAULT '{"per_week": 0}'::jsonb,   -- e.g. {"per_week": 2}
  subject_pool          jsonb NOT NULL DEFAULT '[]'::jsonb,                -- explicit list of subjects
  domain                text,                                             -- LLM proposes when pool empties
  format                text NOT NULL DEFAULT '16:9',
  min_verdict           text NOT NULL DEFAULT 'FEASIBLE'
                          CHECK (min_verdict IN ('FEASIBLE','MARGINAL')),  -- lowest probe verdict to accept
  per_job_threshold_gbp numeric(12,2) NOT NULL DEFAULT 5.00,              -- per-job spend gate
  runtime_target_s      integer NOT NULL DEFAULT 394,                     -- lion benchmark
  n_beats               integer NOT NULL DEFAULT 7,
  next_run_at           timestamptz,                                      -- cadence: when the next run is due
  state                 text NOT NULL DEFAULT 'idle'
                          CHECK (state IN ('idle','producing','paused_spend','paused_ceiling',
                                           'paused_pool','blocked')),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel_id)
);
CREATE UNIQUE INDEX playbooks_public_id_key ON playbooks (public_id);
CREATE TRIGGER playbooks_set_updated_at BEFORE UPDATE ON playbooks
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed a DISABLED wildlife playbook so the shape exists; Banks enables it + fills the pool/cadence.
INSERT INTO playbooks (channel_id, enabled, cadence, subject_pool, domain)
SELECT id, false, '{"per_week": 0}'::jsonb, '[]'::jsonb, 'African wildlife and nature'
  FROM channels WHERE slug = 'wildlife'
ON CONFLICT (channel_id) DO NOTHING;

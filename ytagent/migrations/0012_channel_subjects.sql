-- Slice 6a — channel_subjects: the record of every subject a channel has been offered, with its probe
-- outcome. Two jobs: (1) NO-REPEAT — selection skips subjects already produced/in-flight/rejected;
-- (2) LEARNING-LOOP RAW MATERIAL (Amendment 3) — EVERY proposed subject is recorded with its probe
-- verdict + pool depth, so a later slice can learn which kinds of subject this channel can actually
-- make. History is append-only (a subject may be offered more than once over time); dedup reads the
-- latest status per subject.

CREATE TABLE channel_subjects (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id   uuid NOT NULL DEFAULT gen_random_uuid(),
  channel_id  bigint NOT NULL REFERENCES channels(id),
  subject     text NOT NULL,
  source      text NOT NULL DEFAULT 'pool'
                CHECK (source IN ('pool','domain')),
  status      text NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed','selected','produced','infeasible','failed')),
  verdict     text,          -- the probe verdict when known (FEASIBLE|MARGINAL|INFEASIBLE|INCONCLUSIVE-SHALLOW)
  pool_depth  integer,       -- the probe's E (eligible pool depth) when known
  job_id      bigint REFERENCES jobs(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX channel_subjects_channel_status_idx ON channel_subjects (channel_id, status);
CREATE INDEX channel_subjects_channel_created_idx ON channel_subjects (channel_id, created_at);
CREATE TRIGGER channel_subjects_set_updated_at BEFORE UPDATE ON channel_subjects
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

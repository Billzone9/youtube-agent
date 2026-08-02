-- Slice 6c performance — cache the vision gate's verdict by (source, asset_id, subject). A verdict is a
-- property of the CLIP and the EXPECTED SUBJECT, not of the run — so a resumed or repeated production
-- never re-pays the 3 Haiku frames to re-judge a clip already seen. Keyed to source_film's usage
-- (species+wild, setting observed-not-gated); the stored VisionVerdict is reconstructed on a hit.

CREATE TABLE vision_verdicts (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source      text NOT NULL,
  asset_id    text NOT NULL,
  subject     text NOT NULL,
  verdict     jsonb NOT NULL,      -- serialized VisionVerdict (species/wild/observed setting/features/…)
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, asset_id, subject)
);
CREATE TRIGGER vision_verdicts_set_updated_at BEFORE UPDATE ON vision_verdicts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

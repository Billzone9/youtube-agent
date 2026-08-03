-- Slice 6c gate redesign — sourcing (not the probe verdict) is now the commissioning gate. When a
-- subject fails at the real film-wide sourcing pass, record the ACTUAL clear count so the history shows
-- what sourcing FOUND, not what the 10-clip probe GUESSED. A sourcing-shortfall row is marked
-- verdict='SOURCING_SHORT' (distinct from a cheap probe pool-depth-floor skip) so the consecutive-
-- sourcing-failure cap counts only the expensive failures.

ALTER TABLE channel_subjects ADD COLUMN IF NOT EXISTS clear_count integer;

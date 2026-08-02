-- Slice 6b — the resumable production state machine checkpoints its progress on jobs.stage. Widen the
-- stage vocabulary to admit the six production stages (the coarse original set stays valid). Idempotent.

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_stage_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_stage_check CHECK (
  stage = ANY (ARRAY[
    'research','script','assets','assemble','qc','publish',
    'scripted','sourced','narrated','designed','assembled','submitted'
  ])
);

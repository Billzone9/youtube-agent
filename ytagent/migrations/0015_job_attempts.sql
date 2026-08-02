-- Slice 6c — the scheduler's retry backoff. `attempts` counts tries; `next_attempt_at` gates when a
-- transient-failed job may be retried (deterministic failures do NOT set it — they fail once). A
-- poisoned job cannot spin forever: attempts is bounded and the job goes 'failed' with jobs.error kept.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz;

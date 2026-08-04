-- D2 (2026-08-04) — publish-approval staleness. A publish approval is a point-in-time review of a
-- specific artifact + its metadata; a tap after the TTL (orchestrator._PUBLISH_APPROVAL_TTL, 7 days) is
-- REFUSED, not uploaded, because the review may no longer match the file or the metadata standards
-- (approval 188 went stale within hours). Add 'expired' as a terminal approval state distinct from
-- 'rejected' (a human said no) — 'expired' means the window lapsed, so the audit trail stays honest.
ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_state_check;
ALTER TABLE approvals ADD CONSTRAINT approvals_state_check
  CHECK (state IN ('pending','approved','rejected','expired'));

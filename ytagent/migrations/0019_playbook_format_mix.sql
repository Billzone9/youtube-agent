-- M1 item 4 — the playbook FORMAT MIX. The scheduler rotates through this list per commission so one
-- playbook produces both Shorts and long-form at the intended ratio (A′: ~4 Shorts : ~0.5 long-form/wk
-- → e.g. ["9:16","9:16","9:16","9:16","16:9"] with cadence.per_week set to the TOTAL item rate). Default
-- ["16:9"] preserves existing playbooks exactly (they keep producing long-form only). Config-as-data.
ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS format_mix jsonb NOT NULL DEFAULT '["16:9"]'::jsonb;

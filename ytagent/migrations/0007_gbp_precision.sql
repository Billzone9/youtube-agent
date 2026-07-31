-- Money precision: amount_gbp was numeric(12,2) (pennies), and usage_to_gbp quantised GBP to 2dp.
-- A single Haiku call (~$0.0022 ≈ £0.0017) rounded to £0.00 — invisible in the GBP budget sum — and
-- small Sonnet calls mis-rounded by up to a penny. "Track everything for honest money data" needs
-- sub-penny precision. Widen to numeric(12,4); usage_to_gbp now quantises to 0.0001. Additive + safe
-- (existing 2dp values are preserved; the budget view sums the same column, just more precisely).

ALTER TABLE cost_ledger    ALTER COLUMN amount_gbp TYPE numeric(12,4);
ALTER TABLE revenue_ledger ALTER COLUMN amount_gbp TYPE numeric(12,4);

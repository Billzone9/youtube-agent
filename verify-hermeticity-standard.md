# Verify hermeticity — a binding standard (2026-08-04)

**Every `verify_*.py` that touches the database MUST be hermetic: it leaves ZERO production-state rows
behind.** This is not test hygiene — it is a safety gate. A leftover `pending` publish approval is a
tap-to-upload card the moment the YouTube token is armed. On 2026-08-04, verifies that created
jobs/videos/approvals and never fully cleaned them had accumulated **32 armed publish cards + 9 stuck
jobs** in production state; the token then gained `youtube.force-ssl`, and every one of those cards
became a live-upload-on-tap. A test suite that can cause an accidental upload is a defect, full stop.

## The rule
1. **Hermetic by default.** A DB-touching verify wraps its work in `hermetic(conn)` from
   `scripts/_hermetic.py`. On exit — success OR exception — every row it inserted is deleted
   (high-water mark on `id`, child tables first for FK safety; `cohort_playlists` by `created_at`), and
   the playbook rows are restored to their pre-run `enabled/state/next_run_at` (a verify must never
   leave a playbook armed for an unattended run).
2. **Prove it.** Before the `hermetic` block exits, call `assert_clean(conn, marks)` and fail the verify
   if it returns anything — so the verify demonstrates it did not pollute, rather than trusting it.
3. **Enforced suite-wide.** `scripts/health.py` snapshots the danger tables (`approvals`, `videos`,
   `jobs`) before the suite and asserts **zero net-new rows** after. Any non-hermetic verify makes
   `make health` FAIL. Green health now means "and the tests left no production debris."
4. **New verifies inherit it.** Any new DB verify starts from the `hermetic(conn)` pattern. Pure/offline
   verifies (no DB) are exempt by construction.

## The pattern
```python
from scripts._hermetic import hermetic, assert_clean

conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
async with hermetic(conn) as marks:
    ...                                   # create jobs/videos/approvals, run the pipeline, assert
    leftover = await assert_clean(conn, marks)
    check("verify left no production rows", leftover == [], str(leftover))
# on exit: everything inserted here is gone; the playbook seed rows are back to disabled/idle
```

## What it does NOT cover
`hermetic` restores INSERTs and playbook arming. A verify that UPDATEs some other pre-existing row
(e.g. a channel's config) must snapshot and restore that row itself. When in doubt, prefer creating a
throwaway row over mutating a seed row.

Related: the accidental-upload incident and close-out are recorded in `HANDOVER_M1.md`
(housekeeping_void) and this standard is referenced from `CLAUDE.md`.

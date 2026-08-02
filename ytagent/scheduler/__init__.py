"""The scheduler (Slice 6) — turns a per-channel PLAYBOOK into produced videos, unattended, on a
cadence, surviving restarts. Postgres-backed queue (the `jobs` table) + a polling runner; no broker.

6a (this commit) ships the DATA + SELECTION only: playbook/subject storage and `next_subject`
(no-repeat + the bounded domain proposal loop). The resumable production state machine (6b), the
polling runner + failure routing (6c), and the Telegram control (6d) land in later sub-slices.
"""
from __future__ import annotations

from .selection import CONSECUTIVE_INFEASIBLE_CAP, SubjectPick, next_subject

__all__ = ["next_subject", "SubjectPick", "CONSECUTIVE_INFEASIBLE_CAP"]

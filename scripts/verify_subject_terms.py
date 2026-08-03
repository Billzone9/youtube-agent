"""Regression for the subject-terms FLAG (subject-terms-standard.md). Proves it FLAGS a bare polysemous
term with a suggestion, PASSES clean on a qualified/unambiguous term, and returns advisory data only
(never a block signal). Pure, offline, no DB, no keys. The non-blocking behaviour in the scheduler is
proven separately in verify_scheduler_run.py.

Run: ./.venv/bin/python -m scripts.verify_subject_terms
"""
from __future__ import annotations

import sys

from ytagent.scheduler.subject_terms import flag_if_ambiguous

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


def main():
    print("[1] a bare polysemous term FLAGS with a disambiguation suggestion")
    f = flag_if_ambiguous("lion")
    check("'lion' flagged", f is not None)
    check("carries a suggestion", bool(f and f.get("suggestion")), f and f.get("suggestion"))
    check("carries a reason", bool(f and f.get("reason")))
    check("'seal' (homonym) flagged", flag_if_ambiguous("seal") is not None)

    print("[2] qualified / unambiguous terms PASS clean (no flag)")
    check("'African lion savanna' not flagged (multi-word)", flag_if_ambiguous("African lion savanna") is None)
    check("'elephant' not flagged (unambiguous)", flag_if_ambiguous("elephant") is None)
    check("'african elephant' not flagged", flag_if_ambiguous("african elephant") is None)
    check("empty term not flagged", flag_if_ambiguous("") is None)

    print("[3] the flag is ADVISORY ONLY — its shape carries no block/reject signal")
    f = flag_if_ambiguous("lion")
    check("no 'reject'/'block' key in the flag", not ({"reject", "block", "skip"} & set(f or {})))
    check("keys are exactly term/reason/suggestion",
          set(f.keys()) == {"term", "reason", "suggestion"} if f else False)

    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()

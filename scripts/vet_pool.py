"""Pool vetting (Slice 6c) — measure coverage per candidate subject so the playbook pool is curated from
EVIDENCE, not guesswork. For each candidate it runs a mid-size coverage probe (bigger than the noisy
10-clip verdict), and — separating AMBIGUITY from SCARCITY (subject-terms-standard.md) — RE-PROBES any
underperformer with disambiguated terms ('lion' → 'African lion', 'lioness pride savanna') before
writing it off. Reports estimated film-wide yield per subject + the best (disambiguated) term, ORDERED
most-coverage-first. With --write it stores that ordered, disambiguated pool on the wildlife playbook
(the advisory ordering: the scheduler then tries the best-covered subject first; still only rejected by
real sourcing + the E<5 floor).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.vet_pool [--write] subj1 subj2 ...
"""
from __future__ import annotations

import asyncio
import json
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import repo
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers
from ytagent.sourcing.feasibility import probe_feasibility

_SAMPLE = 20                 # mid-size — more reliable than the 10-clip verdict, cheaper than a source
_WILD_RATIO_FLOOR = 0.6      # below this, the term likely pulls homonyms/captivity → try disambiguation
_DEFAULT = ["African lion", "lion", "cheetah", "leopard", "zebra", "giraffe", "wildebeest",
            "hippopotamus", "african buffalo"]


def _wild_ratio(r):
    return r.both_match / max(r.sampled, 1)


async def _probe(conn, providers, llm, cid, term):
    return await probe_feasibility(conn, providers, term, llm=llm, channel_id=cid, sample_n=_SAMPLE,
                                   runtime_s=340, n_beats=6)


def _disambiguate(llm, subject):
    """CHEAP LLM call: a polysemous/captivity-prone term → 2 sharper, unambiguous WILD search terms."""
    from ytagent.providers.base import CacheableBlock, LLMRequest, ModelTier
    sysb = CacheableBlock(
        "Give 2 precise, UNAMBIGUOUS stock-footage SEARCH terms for a wildlife documentary about the "
        f"WILD '{subject}'. Disambiguate from homonyms (e.g. 'lion' also matches 'sea lion', 'lion "
        "statue') and from captive/zoo footage — name the wild animal in its natural habitat (e.g. "
        "'African lion savanna', 'wild lioness pride'). Return STRICT JSON: {\"terms\": [\"...\",\"...\"]}.")
    try:
        resp = llm.complete(LLMRequest(tier=ModelTier.CHEAP, system=(sysb,),
                                       messages=({"role": "user", "content": subject},),
                                       max_tokens=120, purpose="disambiguate"))
        s = resp.text.strip()
        d = json.loads(s[s.find("{"):s.rfind("}") + 1])
        return [str(x).strip() for x in d.get("terms", []) if str(x).strip()][:2]
    except Exception:  # noqa: BLE001
        return []


async def _vet(conn, providers, llm, cid, subject):
    r = await _probe(conn, providers, llm, cid, subject)
    best_term, best = subject, r
    disamb = False
    if _wild_ratio(r) < _WILD_RATIO_FLOOR:                       # AMBIGUITY suspected → try sharper terms
        for term in _disambiguate(llm, subject):
            r2 = await _probe(conn, providers, llm, cid, term)
            print(f"    ↳ disambiguated '{term}': E={r2.pool_depth} wild={r2.both_match}/{r2.sampled} "
                  f"Y≈{r2.yield_est:.0f}")
            if r2.yield_est > best.yield_est:
                best_term, best, disamb = term, r2, True
    return {"subject": subject, "term": best_term, "E": best.pool_depth, "wild": best.both_match,
            "sampled": best.sampled, "yield": round(best.yield_est), "verdict": best.verdict,
            "disambiguated": disamb, "wild_ratio": round(_wild_ratio(best), 2)}


async def run():
    args = [a for a in sys.argv[1:] if a != "--write"]
    write = "--write" in sys.argv
    candidates = args or _DEFAULT
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        raise SystemExit("prereqs")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")

    print(f"=== POOL VETTING (mid-size probe, sample {_SAMPLE}; disambiguate wild-ratio<{_WILD_RATIO_FLOOR}) ===\n")
    rows = []
    for s in candidates:
        print(f"vetting '{s}'…")
        rows.append(await _vet(conn, providers, llm, ch["id"], s))

    rows.sort(key=lambda r: r["yield"], reverse=True)
    print(f"\n{'term':<26} {'yield':>6} {'E':>4} {'wild':>7} {'ratio':>6}  {'verdict':<20} disamb")
    for r in rows:
        print(f"{r['term']:<26} {r['yield']:>6} {r['E']:>4} {str(r['wild'])+'/'+str(r['sampled']):>7} "
              f"{r['wild_ratio']:>6}  {r['verdict']:<20} {'✓' if r['disambiguated'] else ''}")

    ordered = [r["term"] for r in rows]
    print(f"\nordered pool (most coverage first): {ordered}")
    if write:
        await conn.execute("UPDATE playbooks SET subject_pool=%s WHERE channel_id=%s",
                           [Jsonb(ordered), ch["id"]])
        print("→ written to the wildlife playbook.subject_pool (advisory ordering)")
    else:
        print("(dry run — pass --write to store this ordered pool on the playbook)")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

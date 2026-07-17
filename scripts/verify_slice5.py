"""Zero-spend verification for Slice 5 — no network, no real LLM call.

Uses a FakeLLMProvider (implements the LLMProvider Protocol with canned text + synthetic usage) to
prove the wiring around the real model: tier routing, the guard tripping on an LLM-emitted artifact,
the tell-scanner's lion calibration, and a real cost_ledger write from a fixed usage + seeded prices
(then cleaned up so no fake spend pollutes the honest baseline).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_slice5
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.authoring.tells import scan_tells
from ytagent.config import load_settings
from ytagent.metadata.description import generate_description
from ytagent.metadata.guard import InternalArtifactError
from ytagent.metadata.llm_writer import LLMWriter
from ytagent.providers.base import (
    LLMResponse,
    ModelTier,
    TokenUsage,
    UsageRecord,
)

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


_MODELS = {ModelTier.CHEAP: "claude-haiku-4-5-20251001",
           ModelTier.QUALITY: "claude-sonnet-4-6", ModelTier.PREMIUM: "claude-opus-4-8"}


class FakeLLMProvider:
    """Canned LLMProvider — records the requests it saw + synthetic usage; never touches the network."""

    def __init__(self, sink, scripted) -> None:
        self._sink = sink
        self._scripted = scripted
        self.calls = []

    def model_for(self, tier):
        return _MODELS[tier]

    def complete(self, req) -> LLMResponse:
        self.calls.append(req)
        text = self._scripted(req)
        usage = TokenUsage(input_tokens=1000, output_tokens=200)
        model = _MODELS[req.tier]
        rid = f"fake-{len(self.calls)}"
        self._sink.record(UsageRecord(purpose=req.purpose, model=model, tier=req.tier, usage=usage,
                                      request_id=rid, channel_id=req.channel_id, job_id=req.job_id))
        return LLMResponse(text=text, model=model, usage=usage, request_id=rid)

    def count_tokens(self, req) -> int:
        return 1000

    def submit_batch(self, reqs):  # unused here
        return "fake-batch"

    def retrieve_batch(self, batch_id):
        return {}


class _Sink:
    def __init__(self): self.records = []
    def record(self, rec): self.records.append(rec)


def _good(req):
    if req.purpose == "description":
        return json.dumps({"title": "Wolves of the Northern Wild",
                           "opening": "The grey wolf moves through the snow like a rumour of winter.",
                           "disclosure": "Narration and score are AI-assisted; all footage is licensed stock."})
    if req.purpose == "tags":
        return json.dumps({"tags": ["grey wolf", "wolf documentary", "wildlife documentary"]})
    return "{}"


def _leaky(req):
    if req.purpose == "description":
        return json.dumps({"title": "Wolves", "opening": "See lion-doc-01-footage-manifest.md for shots.",
                           "disclosure": "Narration is AI-assisted; footage licensed."})
    return json.dumps({"tags": ["wolf"]})


class _Research:
    available = False
    notes = ""


async def run() -> None:
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        video = {"topic": "the grey wolf in winter"}

        print("[1] tier routing + honest degradation")
        sink = _Sink()
        fake = FakeLLMProvider(sink, _good)
        writer = LLMWriter(fake)
        parts = writer.write(video=video, channel=channel, research=_Research())
        purposes = [(c.purpose, c.tier) for c in fake.calls]
        check("description prose routed to QUALITY (Sonnet)",
              ("description", ModelTier.QUALITY) in purposes, str(purposes))
        check("tags routed to CHEAP (Haiku)", ("tags", ModelTier.CHEAP) in purposes)
        check("writer returned title+opening+tags", bool(parts["title"] and parts["opening"] and parts["tags"]))
        check("no chapters for an uncut video", parts["chapters"] is None)
        check("usage pushed to sink (billable events captured)", len(sink.records) == len(fake.calls))

        print("[2] the guard still catches an LLM-emitted artifact (writer-output regression)")
        leaky_writer = LLMWriter(FakeLLMProvider(_Sink(), _leaky))
        try:
            generate_description(video, channel, _Research(), leaky_writer)
            check("guard trips on artifact in generated opening", False, "did NOT raise")
        except InternalArtifactError as e:
            check("guard trips on artifact in generated opening", True, str(e)[:60])

        print("[3] tell-scanner treats the lion voice as the reference")
        narr = pathlib.Path("lion-doc-01-narration.md").read_text()
        body = narr.split("---")[1] if "---" in narr else narr
        prose = "\n".join(re.split(r"^##\s+beat\d+\.mp3\s*$", body, flags=re.M)[1:])
        check("scan_tells(lion narration).flagged is False", scan_tells(prose).flagged is False)

        print("[4] cost ledger: fixed usage + seeded prices → expected GBP (then cleaned up)")
        pricing = await repo.ledger.get_llm_pricing(conn)
        rec = UsageRecord(purpose="description", model="claude-sonnet-4-6", tier=ModelTier.QUALITY,
                          usage=TokenUsage(input_tokens=100_000, output_tokens=20_000),
                          request_id="verify-slice5-costtest", channel_id=channel["id"])
        try:
            res = await repo.ledger.write_llm_cost(conn, rec, pricing)
            # sonnet $3/M in, $15/M out: (100000*3 + 20000*15)/1e6 = 0.6 USD; ×0.79 = 0.474 → £0.47
            check("USD computed correctly", res["amount_usd"] == Decimal("0.600000"), str(res["amount_usd"]))
            check("GBP computed correctly", res["amount_gbp"] == Decimal("0.47"), str(res["amount_gbp"]))
            row = res["row"]
            check("ledger row is ai_generation / Anthropic", row["category"] == "ai_generation"
                  and row["provider"] == "Anthropic")
            check("idempotency key set", row["idempotency_key"] == "llm:verify-slice5-costtest")
            check("token metadata stored", row["metadata"].get("input_tokens") == 100_000)
            # idempotent replay → still one row
            await repo.ledger.write_llm_cost(conn, rec, pricing)
            n = (await (await conn.execute(
                "SELECT count(*) n FROM cost_ledger WHERE idempotency_key=%s",
                ["llm:verify-slice5-costtest"])).fetchone())["n"]
            check("replay upserts (no duplicate)", n == 1, f"{n} rows")
        finally:
            await conn.execute("DELETE FROM cost_ledger WHERE idempotency_key=%s",
                               ["llm:verify-slice5-costtest"])
            print("  (cleaned up the fake cost row)")

        print("[5] Slice 5 close-out rules (offline, zero spend)")
        from ytagent.authoring.script import _clean_label, _runtime_violation
        from ytagent.authoring.style import bare_title

        check("title tagline stripped (pipe)",
              bare_title("Lion — Lord of the Savanna | A Cinematic Documentary")
              == "Lion — Lord of the Savanna")
        check("em-dash title preserved (not a tagline)",
              bare_title("Lion — Lord of the Savanna") == "Lion — Lord of the Savanna")

        def _tagline(req):
            if req.purpose == "description":
                return json.dumps({"title": "Wolves of the North | Epic 4K Wildlife",
                                   "opening": "The grey wolf moves through the snow.",
                                   "disclosure": "Narration is AI-assisted; footage licensed."})
            return json.dumps({"tags": ["grey wolf"]})

        p2 = LLMWriter(FakeLLMProvider(_Sink(), _tagline)).write(
            video=video, channel=channel, research=_Research())
        check("LLMWriter emits a bare title (tagline stripped end-to-end)",
              p2["title"] == "Wolves of the North", p2["title"])

        check("beat label de-duplicated ('Beat 3 — X' → 'X')",
              _clean_label("Beat 3 — The huddle") == "The huddle")
        check("clean label unchanged when no prefix",
              _clean_label("The huddle") == "The huddle")

        short = [{"vo": "word " * 80, "approx_seconds": 45} for _ in range(3)]   # 135s, ~240 words
        over = short + [{"vo": "word " * 80, "approx_seconds": 45}]              # 180s > 150×1.15
        check("runtime within budget passes", _runtime_violation(short, 150) is None)
        check("runtime overrun detected (extra beat, like penguin v1→v2)",
              _runtime_violation(over, 150) is not None)
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(run())

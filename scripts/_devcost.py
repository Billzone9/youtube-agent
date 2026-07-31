"""Shared: ledger the LLM spend a calibration/dev script incurred, tagged context='calibration' so it
is distinguishable from production spend. Every script that makes live LLM calls calls this in a finally.
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.config import load_settings


def ledger_calibration_spend(sink, *, context: str = "calibration") -> float:
    """Drain `sink` (a ListUsageSink) to cost_ledger tagged `context`. Returns GBP written."""
    async def _go():
        conn = await psycopg.AsyncConnection.connect(load_settings().dsn(), row_factory=dict_row,
                                                     autocommit=True)
        try:
            pricing = await repo.ledger.get_llm_pricing(conn)
            return await repo.ledger.drain_dev_usage(conn, sink, pricing, context=context)
        finally:
            await conn.close()
    return asyncio.run(_go())

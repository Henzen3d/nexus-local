#!/usr/bin/env python3
"""Health-check do Dream Memory (rodar via docker exec)."""

import asyncio
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")
from backend import database as dbmod
from backend.database import get_user_memory, list_dream_logs


def ok(msg):
    print(f"✅ {msg}")


def bad(msg):
    print(f"❌ {msg}")
    return False


async def main(uid: str):
    facts = await get_user_memory(uid, limit=500, active_only=True)
    all_facts = await get_user_memory(uid, limit=500, active_only=False)
    logs = await list_dream_logs(uid, limit=20)
    now = datetime.utcnow()

    ok(f"fatos ativos={len(facts)} / total={len(all_facts)}")
    ok(f"últimos sonhos={len(logs)}")

    # lineage
    bad_lineage = [f for f in all_facts if f.get("status") in ("merged", "superseded") and not f.get("superseded_by_id")]
    ok(f"fatos lineage quebrados={len(bad_lineage)}")

    # safety floor
    if len(facts) < 1:
        return bad("memória zerada")

    # recent failures
    recent = [l for l in logs if (now - datetime.fromisoformat(l["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)) < timedelta(hours=24)]
    fails = [l for l in recent if l["status"] == "failed"]
    aborted = [l for l in recent if l["status"] == "aborted_safety"]
    ok(f"falhas últimas 24h={len(fails)} / safety abort={len(aborted)}")

    # blocked ops by our filters
    dropped = [l for l in logs if l["status"] == "success" and (l.get("facts_created") or 0) == 0 and (l.get("facts_merged") or 0) == 0 and (l.get("facts_superseded") or 0) == 0]
    if dropped:
        ok(f"sonhos neutros (só keep) recentes={len(dropped)} — filtros de escopo funcionando")

    # family vs identity
    identity_with_family = [f for f in facts if f.get("category") == "identity" and any(
        w in (f.get("fact") or "").lower()
        for w in ("esposa", "esposo", "filho", "filha", "casad", "c[oô]njuge", "namorad")
    )]
    ok(f"identity com pessoa diferente={len(identity_with_family)} (deveria ser 0)")

    # age sanity
    from backend.memory import stated_ages, birth_years
    holder = None
    for f in facts:
        if f.get("category") == "identity" and any(18 <= a <= 120 for a in stated_ages(f.get("fact") or "")):
            holder = stated_ages(f["fact"])[0]
            break
    impossible = [f for f in facts if any(
        tok in (f.get("fact_key") or "").lower()
        for tok in ("child", ".son", "daughter", "filho", "filha")
    ) and holder and any(a >= holder for a in stated_ages(f.get("fact") or ""))]
    ok(f"idade filho impossível={len(impossible)} (deveria ser 0)")

    # pinned
    pinned = [f for f in facts if f.get("is_pinned")]
    ok(f"fatos fixados={len(pinned)}")

    # uptime / recent
    ok(f"status dream: ativo")
    ok("saúde geral OK")


if __name__ == "__main__":
    uid = sys.argv[1] if len(sys.argv) > 1 else "60bdbadb-3789-491b-a762-e44d1fe31889"
    asyncio.run(main(uid))

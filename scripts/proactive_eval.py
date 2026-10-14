#!/usr/bin/env python3
"""Avaliação offline do detector do Assistente Proativo (Fase 1 — F1.4).

Uso (sempre a partir da raiz do repositório, com o Python do .venv):

    # Só o porteiro léxico (sem rede, sem modelo) — métricas do estágio 1
    .venv/bin/python scripts/proactive_eval.py

    # Porteiro + classificador contra um modelo real (chaves vêm do .env)
    PROACTIVE_EVAL_PROVIDER=groq PROACTIVE_EVAL_MODEL=llama-3.1-8b-instant \\
        .venv/bin/python scripts/proactive_eval.py --llm --markdown-out /tmp/f1.md --json-out /tmp/f1.json

    # Também classificar o que o porteiro rejeitou (mede o quanto o porteiro "esconde")
    ... --llm --include-gate-rejected

Variáveis de ambiente:
    PROACTIVE_EVAL_PROVIDER   id do provedor como cadastrado no Nexus (groq, gemini, openrouter, cerebras...)
    PROACTIVE_EVAL_MODEL      nome do modelo COMO ENVIADO À API (ex.: llama-3.1-8b-instant, gemini-2.0-flash)
    PROACTIVE_EVAL_API_KEY    chave a usar; se ausente, cai em <PROVIDER>_API_KEY (ex.: GROQ_API_KEY) do .env

Isolamento (AGENTS.md): este script NUNCA abre ``backend/nexuslocal.db``. Ele cria um
SQLite temporário descartável, aponta ``DB_PATH`` para ele ANTES de importar o backend,
roda ``init_db()`` só para ter o catálogo de provedores (base_url) e apaga tudo ao final.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Isolamento do banco: ANTES de qualquer import de backend.* ───────────────
_TMP_DIR = Path(tempfile.mkdtemp(prefix="nexuslocal-proactive-eval-"))
os.environ["DB_PATH"] = str(_TMP_DIR / "proactive-eval.db")
os.environ.setdefault("JWT_SECRET", "proactive-eval-only-secret-not-for-production-0123456789")
os.environ.setdefault("ATTACHMENTS_SIGNING_SECRET", "proactive-eval-only-attachment-secret")

try:  # chaves de API do .env (opcional)
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except Exception:  # pragma: no cover - dotenv é dependência do backend
    pass

from backend.proactive import evaluation as ev  # noqa: E402

EVAL_USER_ID = "proactive-eval-user"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold", type=Path, default=ev.DEFAULT_GOLD_PATH, help="caminho do JSONL rotulado")
    parser.add_argument("--llm", action="store_true", help="também roda o classificador com um modelo real")
    parser.add_argument("--provider", default=os.getenv("PROACTIVE_EVAL_PROVIDER"), help="id do provedor (env PROACTIVE_EVAL_PROVIDER)")
    parser.add_argument("--model", default=os.getenv("PROACTIVE_EVAL_MODEL"), help="nome do modelo na API (env PROACTIVE_EVAL_MODEL)")
    parser.add_argument("--api-key", default=os.getenv("PROACTIVE_EVAL_API_KEY"), help="chave (env PROACTIVE_EVAL_API_KEY ou <PROVIDER>_API_KEY)")
    parser.add_argument("--sensitivity", default="medium", choices=("low", "medium", "high"))
    parser.add_argument("--concurrency", type=int, default=2, help="chamadas simultâneas ao modelo (padrão 2)")
    parser.add_argument("--timeout", type=float, default=8.0, help="timeout por chamada em segundos (padrão 8)")
    parser.add_argument("--include-gate-rejected", action="store_true", help="classifica também itens rejeitados pelo porteiro")
    parser.add_argument("--limit", type=int, default=0, help="avalia só os N primeiros itens (debug)")
    parser.add_argument("--json-out", type=Path, help="salva registros brutos (sinais, latências, respostas) em JSON")
    parser.add_argument("--markdown-out", type=Path, help="salva o relatório em Markdown")
    parser.add_argument("--quiet", action="store_true", help="não imprime progresso item a item")
    return parser.parse_args(argv)


async def _build_provider(provider_id: str, api_key: str):
    """Resolve o provedor pelo registro real do Nexus, mas dentro do banco TEMPORÁRIO."""
    import aiosqlite

    from backend import database as dbmod
    from backend.providers.registry import get_provider

    assert str(dbmod.DB_PATH).startswith(str(_TMP_DIR)), "DB_PATH não aponta para o diretório temporário!"
    await dbmod.init_db()  # semeia o catálogo de provedores (base_url) no banco temporário
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, ?, ?, 'user')",
            (EVAL_USER_ID, "proactive-eval", "!"),
        )
        await db.execute(
            "INSERT OR REPLACE INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, ?, ?)",
            (EVAL_USER_ID, provider_id, api_key),
        )
        await db.execute("UPDATE providers SET enabled = 1 WHERE id = ?", (provider_id,))
        await db.commit()
        return await get_provider(provider_id, db, user_id=EVAL_USER_ID)


async def _run(args: argparse.Namespace) -> int:
    items = ev.load_gold(args.gold)
    if args.limit:
        items = items[: args.limit]
    print(f"Gold: {len(items)} itens ({sum(i.label for i in items)} positivas) — {args.gold}")

    gate_eval = ev.evaluate_gate(items)
    print()
    print(ev.render_gate_markdown(gate_eval))
    exit_code = 0 if gate_eval.targets_met else 1

    llm_metrics = sweep = None
    model_label = ""
    records: list[ev.LLMRecord] = []
    if args.llm:
        if not args.provider or not args.model:
            print("\n❌ --llm exige --provider/--model (ou PROACTIVE_EVAL_PROVIDER / PROACTIVE_EVAL_MODEL).", file=sys.stderr)
            return 2
        api_key = args.api_key or os.getenv(f"{args.provider.upper().replace('-', '_')}_API_KEY", "")
        if not api_key and args.provider != "ollama":
            print(f"\n❌ Sem chave: defina PROACTIVE_EVAL_API_KEY ou {args.provider.upper()}_API_KEY no .env.", file=sys.stderr)
            return 2
        provider = await _build_provider(args.provider, api_key)
        model_label = f"{args.provider} / {args.model}"
        print(f"\nClassificador: {model_label} · sensibilidade={args.sensitivity} · "
              f"concorrência={args.concurrency} · timeout={args.timeout}s")

        started = time.perf_counter()

        def _progress(rec: ev.LLMRecord) -> None:
            if args.quiet:
                return
            if rec.signal is None:
                print(f"  {rec.id} label={rec.label} porteiro=✗ ({rec.gate_reason})")
                return
            decision = rec.decision(args.sensitivity)
            flag = "✓" if decision.accepted else "✗"
            print(
                f"  {rec.id} label={rec.label} porteiro={'✓' if rec.gate_passed else '✗'} "
                f"LLM={flag} interest={rec.signal.interest:.2f} {rec.signal.entity_type}/{rec.signal.category} "
                f"[{decision.reason}] {rec.meta.latency_ms:.0f} ms"
            )

        records = await ev.evaluate_llm(
            items, provider=provider, model_name=args.model, sensitivity=args.sensitivity,
            concurrency=args.concurrency, timeout=args.timeout,
            include_gate_rejected=args.include_gate_rejected, progress=_progress,
        )
        elapsed = time.perf_counter() - started
        llm_metrics = ev.compute_metrics(records, sensitivity=args.sensitivity)
        sweep = ev.threshold_sweep(records, sensitivity=args.sensitivity)
        print()
        print(ev.render_llm_markdown(llm_metrics, sweep, model_label))
        print(f"\nTempo total do classificador: {elapsed:.1f}s")
        if not llm_metrics.targets_met:
            exit_code = 1

    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(ev.render_markdown(gate_eval, llm_metrics, sweep, model_label), encoding="utf-8")
        print(f"\nRelatório Markdown salvo em {args.markdown_out}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gold": str(args.gold),
            "model": model_label,
            "sensitivity": args.sensitivity,
            "gate": {
                "negatives_rejected": gate_eval.negatives_rejected,
                "negatives": gate_eval.negatives,
                "positives_rejected": gate_eval.positives_rejected,
                "positives": gate_eval.positives,
                "reject_reasons_negatives": dict(gate_eval.reject_reasons_negatives),
                "lost_positives": gate_eval.lost_positives,
                "passed_negatives": gate_eval.passed_negatives,
                "results": {k: v.to_dict() for k, v in gate_eval.results.items()},
            },
            "llm": {
                "precision": llm_metrics.precision, "recall": llm_metrics.recall, "f1": llm_metrics.f1,
                "fp_rate": llm_metrics.fp_rate, "latency_p50_ms": llm_metrics.latency_p50_ms,
                "latency_p95_ms": llm_metrics.latency_p95_ms, "avg_est_tokens": llm_metrics.avg_est_tokens,
                "sweep": [{"threshold": m.threshold, "precision": m.precision, "recall": m.recall,
                           "f1": m.f1, "fp_rate": m.fp_rate} for m in (sweep or [])],
            } if llm_metrics else None,
            "records": [r.to_dict() for r in records],
        }
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Registros brutos salvos em {args.json_out}")

    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run(args))
    finally:
        try:
            from backend.providers.base import close_http_client  # noqa: F401
        except Exception:
            pass
        shutil.rmtree(_TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

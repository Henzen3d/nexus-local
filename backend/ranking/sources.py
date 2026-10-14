"""
backend/ranking/sources.py
Fontes de dados do ranking de modelos.

- ``StaticRegistrySource``  → curadoria local (``backend/data/model_rankings.json``),
  aplicada como *override* de qualidade por nome normalizado (correspondência exata).
- ``OpenRouterRankingSource`` → popularidade global (``/api/v1/models?sort=most-popular``).
- ``resolve_quality``        → qualidade final de um modelo: curadoria > heurística de
  família/geração (``backend/ranking/model_profile.py``), a mesma base usada pelo
  Roteador Inteligente. Nunca aleatória.

Todas as correspondências usam ``normalize_model_key`` para que nomes de provedores
diferentes (``llama3.1:8b`` no Ollama, ``llama-3.1-8b-instant`` no Groq,
``@cf/meta/llama-3.1-8b-instruct-fp8`` na Cloudflare, ``meta-llama/llama-3.1-8b-instruct``
no OpenRouter) convirjam para a mesma chave (``llama-3.1-8b``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

import httpx

from backend.ranking.model_profile import profile_model

logger = logging.getLogger("nexuslocal.ranking.sources")

SOURCE_CURATED = "curated"
SOURCE_HEURISTIC = "heuristic"
# Modelos que não são de chat (embeddings, imagem, TTS, OCR…) recebem no máximo esta
# qualidade: nunca devem vencer um modelo de chat no seletor nem no failover.
NON_CHAT_QUALITY_CAP = 25.0
# Linhas antigas geradas com valores aleatórios (admin.py < 2026-10). São substituídas.
SOURCE_LEGACY_RANDOM = "auto-seed"


class RankingEntry(TypedDict):
    model_id: str
    quality_score: float
    popularity_rank: Optional[int]


# ── Normalização de nomes ────────────────────────────────────────────────────

# Tokens que descrevem variante/quantização/licença, não a família do modelo.
_DROP_TOKENS = frozenset({
    "free", "instruct", "it", "versatile", "instant", "preview", "latest", "exp",
    "experimental", "fast", "fp8", "fp16", "bf16", "awq", "int4", "int8", "gguf",
    "hf", "beta", "alpha", "exacto", "nitro", "online", "extended",
})
_RE_DATE_SUFFIX = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{4}|\d{2}-\d{2}|\d{8}|\d{4})$")
_RE_LEADING_ALPHA_DIGIT = re.compile(r"^([a-z]+)(\d)")


def normalize_model_key(raw: Optional[str]) -> str:
    """Converte nome/ID de modelo em uma chave comparável entre provedores.

    >>> normalize_model_key("@cf/meta/llama-3.1-8b-instruct-fp8")
    'llama-3.1-8b'
    >>> normalize_model_key("llama3.1:8b")
    'llama-3.1-8b'
    >>> normalize_model_key("meta-llama/llama-3.1-8b-instruct")
    'llama-3.1-8b'
    """
    if not raw:
        return ""
    text = str(raw).strip().lower()
    # Descarta o caminho do fornecedor (openai/, @cf/meta/, ~openai/ …)
    if "/" in text:
        text = text.rsplit("/", 1)[1]
    text = re.sub(r"[\s_:]+", "-", text)
    text = re.sub(r"[^a-z0-9.\-]", "", text)
    # Datas / builds ao final (kimi-k2-instruct-0905, gpt-4o-2024-11-20, …)
    for _ in range(2):
        text = _RE_DATE_SUFFIX.sub("", text)
    if text.startswith("meta-llama"):
        text = text[len("meta-"):]
    tokens = []
    for tok in text.split("-"):
        if not tok or tok in _DROP_TOKENS:
            continue
        tok = _RE_LEADING_ALPHA_DIGIT.sub(r"\1-\2", tok)
        tokens.append(tok)
    return "-".join(tokens).strip("-.")


def _key_variants(key: str, max_strips: int = 3) -> List[str]:
    """Chave exata seguida de versões progressivamente mais curtas (sem o último token).

    Só gera variantes que ainda contenham um dígito (versão/tamanho) e ≥ 2 tokens, para
    não casar famílias inteiras por engano (``llama`` sozinho nunca é tentado).
    """
    out = [key]
    parts = key.split("-")
    for _ in range(max_strips):
        if len(parts) <= 2:
            break
        parts = parts[:-1]
        cand = "-".join(parts)
        if any(ch.isdigit() for ch in cand):
            out.append(cand)
    return out


# ── Curadoria local (JSON) ───────────────────────────────────────────────────

class StaticRegistrySource:
    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            self.file_path = Path(__file__).resolve().parents[1] / "data" / "model_rankings.json"
        else:
            self.file_path = file_path

    def load(self) -> Dict[str, Dict]:
        """Reads and returns the local curation of model rankings (chaves cruas)."""
        if not self.file_path.exists():
            logger.warning(f"Static rankings file not found at {self.file_path}")
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("rankings", {})
        except Exception as e:
            logger.error(f"Error loading static rankings: {e}")
            return {}

    def load_index(self) -> Dict[str, Dict]:
        """Curadoria indexada por chave normalizada (uso em ``resolve_quality``)."""
        index: Dict[str, Dict] = {}
        for key, val in self.load().items():
            norm = normalize_model_key(key)
            if norm and isinstance(val, dict):
                index[norm] = val
        return index


# ── OpenRouter (popularidade) ────────────────────────────────────────────────

def build_popularity_index(openrouter_ranks: Dict[str, int]) -> Dict[str, int]:
    """Mapeia ``chave normalizada → melhor posição`` a partir de ``{id OpenRouter: posição}``.

    Variantes do mesmo modelo (``deepseek/deepseek-r1`` e ``deepseek/deepseek-r1:free``)
    colapsam na mesma chave ficando com a melhor (menor) posição.
    """
    index: Dict[str, int] = {}
    for or_id, rank in (openrouter_ranks or {}).items():
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            continue
        key = normalize_model_key(or_id)
        if not key:
            continue
        if key not in index or rank_int < index[key]:
            index[key] = rank_int
    return index


def match_popularity(model_key: str, popularity_index: Dict[str, int]) -> Optional[int]:
    """Posição de popularidade para a chave de um modelo (exata, depois encurtando o nome)."""
    if not model_key or not popularity_index:
        return None
    for cand in _key_variants(model_key):
        rank = popularity_index.get(cand)
        if rank is not None:
            return rank
    return None


class OpenRouterRankingSource:
    def __init__(self, static_source: Optional[StaticRegistrySource] = None):
        self.static_source = static_source or StaticRegistrySource()
        self.api_url = "https://openrouter.ai/api/v1/models"

    async def fetch_popularity_ranks(self) -> Dict[str, int]:
        """Fetches models from OpenRouter ordered by popularity and maps their ranks."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params={"sort": "most-popular"})
                if response.status_code == 200:
                    data = response.json()
                    models_list = data.get("data", [])
                    ranks = {}
                    for idx, model in enumerate(models_list):
                        model_id = model.get("id")
                        if model_id:
                            ranks[model_id] = idx + 1
                    return ranks
                else:
                    logger.warning(f"OpenRouter returned status code {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching rankings from OpenRouter: {e}")
        return {}

    async def fetch(self) -> List[RankingEntry]:
        """(Legado) Entradas da curadoria local com popularidade dinâmica do OpenRouter."""
        static_rankings = self.static_source.load()
        popularity_index = build_popularity_index(await self.fetch_popularity_ranks())
        entries: List[RankingEntry] = []
        for key, val in static_rankings.items():
            quality = float(val.get("quality_score", 0.0) or 0.0)
            pop_rank = match_popularity(normalize_model_key(key), popularity_index)
            if pop_rank is None:
                pop_rank = val.get("popularity_rank")
            entries.append({"model_id": key, "quality_score": quality, "popularity_rank": pop_rank})
        return entries


# ── Qualidade final ──────────────────────────────────────────────────────────

def model_key_for(model_id: str, name: Optional[str]) -> str:
    """Chave normalizada de um modelo cadastrado (prefere o nome; cai para o ID)."""
    return normalize_model_key(name) or normalize_model_key(model_id)


def resolve_quality(
    model_id: str,
    name: Optional[str],
    provider_id: Optional[str],
    reasoning_control: Optional[str] = None,
    supports_vision: int = 0,
    curated_index: Optional[Dict[str, Dict]] = None,
) -> Tuple[float, str]:
    """Qualidade (0–100) determinística de um modelo e a origem do valor.

    1. Curadoria local (``model_rankings.json``) por chave normalizada exata → ``curated``.
    2. Heurística de família/geração do perfil (mesma base do roteador) → ``heuristic``.
    Modelos não conversacionais (imagem, embeddings, TTS…) ficam limitados a
    ``NON_CHAT_QUALITY_CAP`` para nunca liderarem o seletor nem o failover.
    """
    key = model_key_for(model_id, name)
    prof = profile_model(model_id, name or "", provider_id or "", reasoning_control, int(supports_vision or 0))
    quality, source = float(prof.baseline_quality), SOURCE_HEURISTIC
    if curated_index and key in curated_index:
        try:
            quality = max(0.0, min(float(curated_index[key].get("quality_score")), 100.0))
            source = SOURCE_CURATED
        except (TypeError, ValueError):
            pass
    if not prof.is_chat_capable:
        quality = min(quality, NON_CHAT_QUALITY_CAP)
    return quality, source

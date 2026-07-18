import json
import re
import hashlib
import aiosqlite
from backend.database import (
    add_memory_fact,
    deactivate_memory_by_key,
    get_user_memory,
    get_memory_summary,
    upsert_memory_summary,
    delete_memory_summary,
    delete_orphaned_memory_summaries,
    clear_all_memory_summaries,
    get_conversation_project_tag,
    mark_conversation_memory_extracted,
    list_idle_conversations_for_memory,
    MEMORY_IDLE_MINUTES,
    MEMORY_IDLE_MAX_AGE_DAYS,
    MEMORY_IDLE_BATCH,
    DB_PATH,
    MEMORY_CATEGORIES,
    MEMORY_INJECT_MAX_CHARS,
    MEMORY_INJECT_LIMIT,
)
from backend.providers.registry import get_provider, get_model_name
from backend.logging_config import get_logger

logger = get_logger(__name__)

# Cap for summary section inside system block (richer profiles need more room)
MEMORY_SUMMARY_MAX_CHARS = 2800
MEMORY_IMPORT_MAX_FACTS = 90
MEMORY_IMPORT_FACT_MAX_CHARS = 420

# System prompt for the background memory extractor agent
_EXTRACTOR_SYSTEM = (
    "Você é um agente de extração de memória em segundo plano.\n"
    "Analise a conversa recente e extraia FATOS DURÁVEIS.\n\n"
    "REGRA CRÍTICA — SUJEITO DO FATO:\n"
    "- O TITULAR da conta (\"usuário\") é a pessoa que fala em USER:.\n"
    "- Filhos, cônjuge, parentes, colegas, professores, personagens de escola = OUTRAS PESSOAS.\n"
    "- NUNCA grave idade, escola, série/ano escolar, turma ou brinquedo de um FILHO/DEPENDENTE "
    "como se fossem do usuário.\n"
    "- Se o usuário fala do filho (ex.: \"meu filho tem 10 anos\", \"estuda no Zulma\", "
    "\"4ª série\"), o fact_key DEVE começar com family. e o texto DEVE nomear o parentesco "
    "(ex.: \"Filho Nicolas Héron: 10 anos, Escola Zulma, 4ª série\").\n"
    "- Se o usuário fala da esposa/esposo/cônjuge (ex.: \"minha esposa Vera Lúcia\"), "
    "use family.spouse_* e o texto DEVE começar com o parentesco específico "
    "(ex.: \"Esposa Vera Lúcia\"). NUNCA use só o nome nem o rótulo genérico \"familiar\".\n"
    "- identity.* é APENAS do usuário (nome, apelido, idade do próprio usuário se ele disser "
    "\"eu tenho X anos\" de forma inequívoca sobre si).\n"
    "- Em dúvida se um atributo é do usuário ou de familiar → use family.* e deixe o parentesco "
    "explícito no texto (Filho/Filha/Esposa/Esposo/Cônjuge — nunca só \"familiar\").\n\n"
    "Extraia: identidade do usuário, trabalho/empresa do usuário, família (com parentesco), "
    "projetos em andamento, stack/ferramentas, preferências estáveis.\n\n"
    "NÃO extraia: saudações, pedidos pontuais, senhas, tokens, chaves de API, "
    "dados sensíveis sem necessidade, ou informações sem certeza clara.\n\n"
    "Categorias válidas: professional | personal | project | preference | identity | tech\n"
    "(fatos de família usam category=personal e fact_key family.*)\n\n"
    "fact_key estável em snake_case:\n"
    "- identity.first_name, identity.full_name, identity.age (só se for DO usuário)\n"
    "- family.child_name, family.child_age, family.child_school, family.child_profile\n"
    "- family.spouse_name, family.spouse_profile\n"
    "- work.company, work.role, project.*, prefs.*, tech.*\n\n"
    "PARENTESCO NO TEXTO (obrigatório para family.*):\n"
    "- Filho/Filha + nome (+ idade/escola se houver)\n"
    "- Esposa/Esposo/Cônjuge + nome\n"
    "- Proibido gravar só \"Vera Lúcia\" ou \"Nicolas Héron\" sem parentesco\n"
    "- Proibido o rótulo genérico \"familiar\" quando o parentesco for conhecido\n\n"
    "Se um fato antigo está ERRADO (ex.: idade do filho gravada como do usuário), "
    "inclua action=forget nesse fact_key e um upsert correto em family.*.\n\n"
    "Retorne APENAS um JSON array puro (sem markdown, sem comentários):\n"
    "[\n"
    "  {\"fact_key\": \"identity.first_name\", \"category\": \"identity\", "
    "\"fact\": \"Osmar\", \"confidence\": 0.95, \"action\": \"upsert\"},\n"
    "  {\"fact_key\": \"family.spouse_name\", \"category\": \"personal\", "
    "\"fact\": \"Esposa Vera Lúcia\", \"confidence\": 0.95, \"action\": \"upsert\"},\n"
    "  {\"fact_key\": \"family.child_profile\", \"category\": \"personal\", "
    "\"fact\": \"Filho Nicolas Héron: 10 anos, Escola Zulma, 4ª série\", "
    "\"confidence\": 0.9, \"action\": \"upsert\"},\n"
    "  {\"fact_key\": \"identity.age\", \"category\": \"identity\", "
    "\"fact\": \"\", \"confidence\": 0.0, \"action\": \"forget\"}\n"
    "]\n"
    "Se não houver fatos novos ou alterações, retorne []."
)

# --- Anti-confusão usuário × família -----------------------------------------

_RE_FAMILY_WORD = re.compile(
    r"\b(filho|filha|filho\(a\)|son|daughter|esposa|esposo|marido|mulher|"
    r"wife|husband|spouse|c[oô]njuge|esposa|namorad[oa]|pai|m[aã]e|irmão|irmao|irmã|irma|"
    r"neto|neta|sobrinho|sobrinha|primo|prima|familiar|dependente)\b",
    re.I,
)
# Specific kinship (not the generic "familiar")
_RE_SPECIFIC_KINSHIP = re.compile(
    r"\b(filho|filha|filho\(a\)|son|daughter|esposa|esposo|marido|mulher|"
    r"wife|husband|spouse|c[oô]njuge|namorad[oa]|pai|m[aã]e|irmão|irmao|irmã|irma|"
    r"neto|neta|sobrinho|sobrinha|primo|prima)\b",
    re.I,
)
_RE_GENERIC_FAMILIAR_PREFIX = re.compile(
    r"^\s*familiar(\s*\(\s*n[aã]o\s+o\s+usu[aá]rio\s*\))?\s*[:\-–—]?\s*",
    re.I,
)
_RE_CHILD_SCHOOL = re.compile(
    r"\b(\d{1,2})\s*anos?\b|"
    r"\b(\d{1,2})[ªaºo°]?\s*s[eé]rie\b|"
    r"\b(ensino\s+fundamental|educa[cç][aã]o\s+infantil|pr[eé]-?escola|"
    r"jardim\s+de\s+inf[aâ]ncia|escola\s+\w+)\b",
    re.I,
)
_RE_USER_SELF_AGE = re.compile(
    r"\b(eu\s+tenho|tenho)\s+(\d{1,2})\s*anos\b|"
    r"\bminha\s+idade\b|"
    r"\bidade\s*[:=]\s*(\d{1,2})\b",
    re.I,
)
_RE_LIKELY_CHILD_AGE = re.compile(r"\b([5-9]|1[0-5])\s*anos?\b", re.I)
_RE_GRADE = re.compile(r"\b(\d{1,2})[ªaºo°]?\s*s[eé]rie\b", re.I)
_RE_SCHOOL_NAME = re.compile(r"\bescola\b", re.I)

# Canonical PT labels for family fact_keys (avoid collapsing to "familiar")
_KINSHIP_FROM_KEY = (
    (("spouse", "wife", "esposa", "husband", "esposo", "conjuge", "cônjuge", "partner"), "Cônjuge"),
    (("child", "son", "daughter", "filho", "filha", "kid", "dependente"), "Filho(a)"),
    (("father", "pai"), "Pai"),
    (("mother", "mae", "mãe"), "Mãe"),
    (("sibling", "brother", "sister", "irmao", "irmão", "irma", "irmã"), "Irmão(ã)"),
)


def _is_family_key(fact_key: str | None) -> bool:
    k = (fact_key or "").lower()
    return k.startswith("family.") or k.startswith("fam.") or ".child" in k or ".spouse" in k


def _looks_like_child_or_school_attr(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _RE_FAMILY_WORD.search(t):
        return True
    if _RE_GRADE.search(t):
        return True
    if _RE_SCHOOL_NAME.search(t) and _RE_LIKELY_CHILD_AGE.search(t):
        return True
    if _RE_SCHOOL_NAME.search(t) and len(t) < 80:
        return True
    # bare young age without "eu tenho"
    if _RE_LIKELY_CHILD_AGE.search(t) and not _RE_USER_SELF_AGE.search(t) and len(t) < 40:
        return True
    return False


def _kinship_label_from_key(fact_key: str | None) -> str | None:
    """Map family.* fact_key → canonical Portuguese kinship label."""
    k = (fact_key or "").lower()
    if not k:
        return None
    for tokens, label in _KINSHIP_FROM_KEY:
        if any(tok in k for tok in tokens):
            return label
    return None


def _kinship_label_from_text(fact: str) -> str | None:
    """If text already has a *specific* kinship word, return a canonical label."""
    t = (fact or "").strip()
    if not t:
        return None
    m = _RE_SPECIFIC_KINSHIP.search(t)
    if not m:
        return None
    w = m.group(1).lower()
    mapping = {
        "filho": "Filho",
        "filha": "Filha",
        "filho(a)": "Filho(a)",
        "son": "Filho",
        "daughter": "Filha",
        "esposa": "Esposa",
        "esposo": "Esposo",
        "marido": "Esposo",
        "mulher": "Esposa",
        "wife": "Esposa",
        "husband": "Esposo",
        "spouse": "Cônjuge",
        "cônjuge": "Cônjuge",
        "conjuge": "Cônjuge",
        "namorada": "Namorada",
        "namorado": "Namorado",
        "pai": "Pai",
        "mãe": "Mãe",
        "mae": "Mãe",
        "irmão": "Irmão",
        "irmao": "Irmão",
        "irmã": "Irmã",
        "irma": "Irmã",
        "neto": "Neto",
        "neta": "Neta",
        "sobrinho": "Sobrinho",
        "sobrinha": "Sobrinha",
        "primo": "Primo",
        "prima": "Prima",
    }
    return mapping.get(w, w.capitalize())


def _strip_generic_familiar_prefix(fact: str) -> str:
    """Remove vague 'Familiar (não o usuário):' so we can re-prefix with real kinship."""
    t = (fact or "").strip()
    # Also strip trailing "(familiar)" style suffixes the LLM summary sometimes adds
    t = re.sub(r"\s*\(\s*familiar\s*\)\s*$", "", t, flags=re.I)
    t = _RE_GENERIC_FAMILIAR_PREFIX.sub("", t).strip()
    return t


def _infer_kinship_label(fact_key: str | None, fact: str) -> str:
    """
    Prefer specific kinship (Esposa/Filho) over generic 'Familiar'.
    Order: explicit text → fact_key → child/school heuristics → Familiar.
    """
    specific = _kinship_label_from_text(fact)
    if specific:
        return specific
    from_key = _kinship_label_from_key(fact_key)
    core = _strip_generic_familiar_prefix(fact)
    if from_key:
        # Refine Filho(a)/Cônjuge with light gender cues in the name/text
        if from_key == "Filho(a)":
            if re.search(r"\bfilha\b", fact or "", re.I):
                return "Filha"
            if re.search(r"\bfilho\b", fact or "", re.I):
                return "Filho"
            # Common masculine ending heuristic only when name is bare
            if re.search(r"\b(nicolas|nicholas|jo[aã]o|pedro|lucas|gabriel|miguel)\b", core, re.I):
                return "Filho"
            if re.search(r"\b(ana|maria|julia|júlia|beatriz|laura|sofia)\b", core, re.I):
                return "Filha"
            return "Filho(a)"
        if from_key == "Cônjuge":
            if re.search(r"\b(esposa|mulher|wife)\b", fact or "", re.I):
                return "Esposa"
            if re.search(r"\b(esposo|marido|husband)\b", fact or "", re.I):
                return "Esposo"
            # Feminine multi-word names common in BR (Vera Lúcia, etc.) — soft default Esposa
            # only when key is spouse and no male marker
            if re.search(r"\b(vera|l[uú]cia|lucia|maria|ana|juliana|fernanda|patricia|patrícia)\b", core, re.I):
                return "Esposa"
            return "Cônjuge"
        return from_key
    # Age/school alone (without spouse/child key) → child attr — NOT mere word "familiar"
    if _RE_GRADE.search(fact or "") or _RE_SCHOOL_NAME.search(fact or "") or (
        _RE_LIKELY_CHILD_AGE.search(fact or "") and not _RE_USER_SELF_AGE.search(fact or "")
    ):
        return "Filho(a)"
    return "Familiar"


def _enrich_family_fact(fact_key: str | None, fact: str) -> str:
    """
    Ensure family facts start with a specific kinship label.
    Upgrades 'Familiar (não o usuário): X' → 'Esposa X' / 'Filho X' when possible.
    """
    raw = (fact or "").strip()
    if not raw:
        return raw

    # Already has specific kinship → keep (but clean pure-generic wrapper if mixed)
    if _RE_SPECIFIC_KINSHIP.search(raw) and not _RE_GENERIC_FAMILIAR_PREFIX.match(raw):
        return raw

    core = _strip_generic_familiar_prefix(raw)
    if not core:
        return raw

    # If after strip it already has specific kinship, keep
    if _RE_SPECIFIC_KINSHIP.search(core):
        return core

    label = _infer_kinship_label(fact_key, raw)
    # Avoid "Familiar Familiar: …"
    if core.lower().startswith(label.lower()):
        return core
    return f"{label} {core}"


def _sanitize_extracted_item(item: dict) -> dict | None:
    """
    Normalize extractor output so family attributes never land on identity.*.
    Returns None to drop the item.
    """
    if not isinstance(item, dict):
        return None

    action = (item.get("action") or "upsert").strip().lower()
    fact_key = (item.get("fact_key") or "").strip().lower().replace(" ", "_")
    category = (item.get("category") or "preference").strip()
    fact = (item.get("fact") or "").strip()

    try:
        confidence = float(item.get("confidence", 0.8))
    except (TypeError, ValueError):
        confidence = 0.8

    if category not in MEMORY_CATEGORIES:
        category = "preference"

    if action == "forget":
        if not fact_key:
            return None
        return {
            "action": "forget",
            "fact_key": fact_key,
            "category": category,
            "fact": "",
            "confidence": 0.0,
        }

    if not fact:
        return None

    # Force family.* for relative-related content
    if _is_family_key(fact_key) or _RE_FAMILY_WORD.search(fact) or (
        category == "identity" and _looks_like_child_or_school_attr(fact)
    ):
        if not _is_family_key(fact_key):
            # Remap common wrong identity keys
            if fact_key in ("identity.age", "age", "identity.idade"):
                fact_key = "family.child_age"
            elif "school" in fact_key or "escola" in fact_key:
                fact_key = "family.child_school"
            elif "serie" in fact_key or "série" in fact_key or "grade" in fact_key:
                fact_key = "family.child_grade"
            elif "spouse" in fact_key or "esposa" in fact_key or "esposo" in fact_key:
                fact_key = "family.spouse_name"
            elif fact_key.startswith("identity."):
                fact_key = "family." + fact_key.split(".", 1)[-1]
            else:
                fact_key = fact_key if fact_key else "family.note"
                if not fact_key.startswith("family."):
                    fact_key = f"family.{fact_key}"
        category = "personal"
        fact = _enrich_family_fact(fact_key, fact)

    # identity.age with school/grade → family
    if category == "identity" and _looks_like_child_or_school_attr(fact):
        category = "personal"
        if not _is_family_key(fact_key):
            fact_key = "family.child_profile"
        fact = _enrich_family_fact(fact_key, fact)

    # Bare school/grade/young age under identity without family key
    if category == "identity" and fact_key in (
        "identity.age",
        "identity.school",
        "identity.grade",
        "identity.escola",
        "identity.serie",
    ):
        if _looks_like_child_or_school_attr(fact) or not _RE_USER_SELF_AGE.search(fact):
            category = "personal"
            fact_key = {
                "identity.age": "family.child_age",
                "identity.school": "family.child_school",
                "identity.escola": "family.child_school",
                "identity.grade": "family.child_grade",
                "identity.serie": "family.child_grade",
            }.get(fact_key, "family.child_profile")
            fact = _enrich_family_fact(fact_key, fact)

    # Final pass: any family key still with only generic "familiar" gets upgraded
    if _is_family_key(fact_key):
        fact = _enrich_family_fact(fact_key, fact)

    return {
        "action": "upsert",
        "fact_key": fact_key or None,
        "category": category,
        "fact": fact,
        "confidence": confidence,
    }


async def repair_identity_family_confusion(user_id: str) -> int:
    """
    One-shot / on-refresh fix:
      1) demote identity facts that look like child/school attributes
      2) upgrade generic "Familiar …" labels to Esposa/Filho when fact_key allows
    Returns number of facts reclassified or relabeled.
    """
    facts = await get_user_memory(user_id, limit=200, active_only=True)
    if not facts:
        return 0

    has_adult_signal = False
    for f in facts:
        cat = (f.get("category") or "").lower()
        text = (f.get("fact") or "").lower()
        key = (f.get("fact_key") or "").lower()
        if cat == "professional" or key.startswith("work.") or key.startswith("professional."):
            has_adult_signal = True
            break
        if any(
            w in text
            for w in (
                "empresa",
                "trabalho",
                "sócio",
                "socio",
                "dono",
                "ceo",
                "dev",
                "developer",
                "engenheiro",
                "serviços",
                "servicos",
                "comedian",
                "comediante",
            )
        ):
            has_adult_signal = True
            break

    if not has_adult_signal:
        # Still demote identity school/grade which almost never belong to identity alone
        pass

    fixed = 0
    for f in facts:
        cat = (f.get("category") or "").lower()
        key = (f.get("fact_key") or "").lower()
        text = (f.get("fact") or "").strip()
        if not text:
            continue

        should_demote = False
        if cat == "identity" and _looks_like_child_or_school_attr(text):
            should_demote = True
        if cat == "identity" and key in (
            "identity.age",
            "identity.school",
            "identity.grade",
            "identity.escola",
            "identity.serie",
        ):
            if has_adult_signal or _looks_like_child_or_school_attr(text):
                should_demote = True
        # Personal bullets that are bare child age/school without family prefix
        if cat == "personal" and not _is_family_key(key) and _looks_like_child_or_school_attr(text):
            if not _RE_FAMILY_WORD.search(text) and (
                _RE_GRADE.search(text) or _RE_SCHOOL_NAME.search(text) or _RE_LIKELY_CHILD_AGE.search(text)
            ):
                should_demote = True

        # --- Path A: demote identity/personal → family.* ---
        if should_demote:
            old_key = key or None
            new_key = "family.child_profile"
            if _RE_LIKELY_CHILD_AGE.search(text) and len(text) < 30:
                new_key = "family.child_age"
            elif _RE_SCHOOL_NAME.search(text):
                new_key = "family.child_school"
            elif _RE_GRADE.search(text):
                new_key = "family.child_grade"

            new_fact = _enrich_family_fact(new_key, text)

            try:
                if old_key:
                    await deactivate_memory_by_key(user_id, old_key)
                await add_memory_fact(
                    user_id=user_id,
                    category="personal",
                    fact=new_fact,
                    fact_key=new_key,
                    source_conv_id=f.get("source_conv_id"),
                    confidence=float(f.get("confidence") or 0.7),
                )
                if not old_key and f.get("id"):
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute(
                            "UPDATE user_memory SET is_active = 0, updated_at = datetime('now') "
                            "WHERE id = ? AND user_id = ?",
                            (f["id"], user_id),
                        )
                        await db.commit()
                fixed += 1
            except Exception as e:
                logger.error("[Memory Repair] falha ao reclassificar fato:", exc_info=e)
            continue

        # --- Path B: upgrade generic "Familiar" / bare names under family.* only ---
        # Safe scope: family.* keys, or text already tagged as familiar/kinship.
        has_generic = bool(_RE_GENERIC_FAMILIAR_PREFIX.match(text)) or bool(
            re.search(r"\(\s*familiar\s*\)", text, re.I)
        )
        has_specific = bool(_RE_SPECIFIC_KINSHIP.search(text))
        if not (_is_family_key(key) or has_generic or has_specific):
            continue

        enriched = _enrich_family_fact(key if _is_family_key(key) else None, text)
        new_key = key if _is_family_key(key) else key
        if not _is_family_key(new_key):
            label = _infer_kinship_label(None, enriched)
            if label in ("Esposa", "Esposo", "Cônjuge", "Namorada", "Namorado"):
                new_key = "family.spouse_name"
            elif label in ("Filho", "Filha", "Filho(a)"):
                new_key = "family.child_name"
            elif has_generic or has_specific:
                new_key = "family.note"
            else:
                continue

        if enriched == text and (new_key or "") == (key or ""):
            continue

        try:
            if key and key != new_key:
                await deactivate_memory_by_key(user_id, key)
            await add_memory_fact(
                user_id=user_id,
                category="personal",
                fact=enriched,
                fact_key=new_key or None,
                source_conv_id=f.get("source_conv_id"),
                confidence=float(f.get("confidence") or 0.75),
            )
            if not key and f.get("id") and enriched != text:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE user_memory SET is_active = 0, updated_at = datetime('now') "
                        "WHERE id = ? AND user_id = ?",
                        (f["id"], user_id),
                    )
                    await db.commit()
            fixed += 1
        except Exception as e:
            logger.error("[Memory Repair] falha ao enriquecer parentesco:", exc_info=e)

    if fixed:
        logger.info(
            "[Memory Repair] user=%s: %s fato(s) reclassificado(s)/enriquecido(s) (family/parentesco)",
            user_id,
            fixed,
        )
    return fixed


async def _get_meta(db, key: str) -> str | None:
    try:
        async with db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0].strip() if row and row[0] else None
    except Exception:
        return None


async def is_memory_extractor_enabled(db) -> bool:
    """Auto-extraction can be disabled via meta.memory_extractor_enabled = '0'."""
    val = await _get_meta(db, "memory_extractor_enabled")
    if val is None:
        return True
    return val not in ("0", "false", "False", "no", "off")


async def _get_extractor_provider_and_model(db, fallback_provider_id: str, fallback_model_id: str, user_id: str):
    """
    Waterfall for cheap extractor model:
      1. Dedicated memory extractor (meta.memory_extractor_*)
      2. Enhancer config table (usually a small model)
      3. Current chat provider/model (last resort)
    """
    # 1. Dedicated memory extractor settings (meta)
    mem_provider = await _get_meta(db, "memory_extractor_provider_id")
    mem_model = await _get_meta(db, "memory_extractor_model_id")

    if mem_provider and mem_model:
        try:
            provider = await get_provider(mem_provider, db, user_id=user_id)
            model_name = await get_model_name(mem_model, db)
            return provider, model_name, "memory_extractor"
        except Exception:
            pass

    # 2. Enhancer settings (enhancer_config table — not meta)
    try:
        async with db.execute(
            "SELECT enhancer_provider_id, enhancer_model_id FROM enhancer_config WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] and row[1]:
            try:
                provider = await get_provider(row[0], db, user_id=user_id)
                model_name = await get_model_name(row[1], db)
                return provider, model_name, "enhancer"
            except Exception:
                pass
    except Exception:
        pass

    # 3. Final fallback: same provider/model as the chat
    provider = await get_provider(fallback_provider_id, db, user_id=user_id)
    model_name = await get_model_name(fallback_model_id, db)
    return provider, model_name, "chat_fallback"


async def extract_user_memory_background(
    user_id: str, conversation_id: str, model_id: str, provider_id: str
):
    """
    Runs in the background after each assistant response to extract durable facts or
    preferences about the user from the most recent messages.
    Implements: fact_key UPSERT, action:forget (soft-delete), model waterfall, and token cap.
    """
    try:
        # 1. Fetch last 12 messages and resolve provider/model — open/close DB fast
        async with aiosqlite.connect(DB_PATH) as db:
            if not await is_memory_extractor_enabled(db):
                return
            async with db.execute(
                """SELECT role, content FROM messages
                   WHERE conversation_id = ?
                   ORDER BY created_at DESC LIMIT 12""",
                (conversation_id,)
            ) as cur:
                rows = await cur.fetchall()

            if not rows:
                return

            rows.reverse()  # chronological order

            # Build readable history
            history_text = ""
            for role, content in rows:
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = " ".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                else:
                    continue
                history_text += f"{role.upper()}: {text}\n"

            try:
                provider, model_name, source = await _get_extractor_provider_and_model(
                    db, provider_id, model_id, user_id
                )
            except Exception as prov_err:
                logger.error("[Memory Extractor] Erro ao resolver provider/modelo:", exc_info=prov_err)
                return

        # 2. Call the LLM (outside the DB connection to avoid holding it during network I/O)
        messages = [
            {"role": "system", "content": _EXTRACTOR_SYSTEM},
            {"role": "user", "content": f"Conversa recente:\n{history_text}"},
        ]
        full_response = ""
        try:
            async for token in provider.stream_chat(model=model_name, messages=messages, temperature=0.05):
                full_response += str(token)
        except Exception as api_err:
            logger.error("[Memory Extractor] Erro na chamada ao LLM (source=%s):", source, exc_info=api_err)
            return

        # 3. Clean up potential markdown fences
        full_response = full_response.strip()
        if full_response.startswith("```"):
            lines = full_response.splitlines()
            if len(lines) >= 3:
                full_response = "\n".join(lines[1:-1]).strip()

        # 4. Parse and persist
        try:
            items = json.loads(full_response)
            if not isinstance(items, list):
                return

            saved = 0
            forgotten = 0
            for raw_item in items:
                item = _sanitize_extracted_item(raw_item)
                if not item:
                    continue

                action = item.get("action", "upsert")
                fact_key = item.get("fact_key") or None
                category = item.get("category", "preference")
                fact = item.get("fact", "")
                confidence = float(item.get("confidence", 0.8))

                if action == "forget" and fact_key:
                    await deactivate_memory_by_key(user_id, fact_key)
                    forgotten += 1
                elif action == "upsert" and fact:
                    await add_memory_fact(
                        user_id=user_id,
                        category=category,
                        fact=fact,
                        fact_key=fact_key,
                        source_conv_id=conversation_id,
                        confidence=confidence,
                    )
                    saved += 1

            # Always stamp extraction time so idle job does not re-run forever on parse issues
            try:
                await mark_conversation_memory_extracted(conversation_id)
            except Exception as stamp_err:
                logger.error("[Memory Extractor] stamp error:", exc_info=stamp_err)

            # Repara confusão identidade×família mesmo se o extrator não salvou nada novo
            try:
                repaired = await repair_identity_family_confusion(user_id)
            except Exception as rep_err:
                logger.info("[Memory Repair] %s", rep_err)
                repaired = 0

            if saved > 0 or forgotten > 0 or repaired > 0:
                logger.info(
                    "[Memory Extractor] user=%s: +%s upserted, -%s forgotten, ~%s repaired",
                    user_id, saved, forgotten, repaired,
                )
                # Phase D: local extraction metrics
                try:
                    from backend.database import increment_memory_extraction_stats

                    await increment_memory_extraction_stats(user_id)
                except Exception as st_err:
                    logger.info("[Memory Stats] %s", st_err)
                # Phase C2/E: refresh rolling summaries (deterministic + optional LLM)
                try:
                    await refresh_memory_summaries(
                        user_id,
                        conversation_id,
                        provider_id=provider_id,
                        model_id=model_id,
                        use_llm=True,
                    )
                except Exception as sum_err:
                    logger.error("[Memory Summaries] Erro ao atualizar resumos:", exc_info=sum_err)
            else:
                # Even with no new facts, mark extracted so idle job advances
                pass
        except Exception as parse_err:
            logger.error(
                "[Memory Extractor] Erro ao decodificar JSON: %s. Resposta: %s",
                parse_err, full_response[:200],
            )
            # Still mark extracted to avoid hammering the same dead JSON forever
            try:
                await mark_conversation_memory_extracted(conversation_id)
            except Exception:
                pass

    except Exception as e:
        logger.error("[Memory Extractor] Erro geral:", exc_info=e)


async def process_idle_memory_extractions(
    idle_minutes: int = MEMORY_IDLE_MINUTES,
    max_age_days: int = MEMORY_IDLE_MAX_AGE_DAYS,
    batch: int = MEMORY_IDLE_BATCH,
) -> int:
    """
    M4: scan idle conversations and run background extraction.
    Returns number of conversations processed.
    """
    try:
        candidates = await list_idle_conversations_for_memory(
            idle_minutes=idle_minutes,
            max_age_days=max_age_days,
            limit=batch,
        )
    except Exception as e:
        logger.error("[Memory Idle Job] list error:", exc_info=e)
        return 0

    if not candidates:
        return 0

    processed = 0
    for c in candidates:
        user_id = c.get("user_id")
        conv_id = c.get("conversation_id")
        model_id = c.get("model_id") or ""
        provider_id = c.get("provider_id") or ""
        if not user_id or not conv_id:
            continue
        # Skip if we have no model/provider to fall back to — still try enhancer path
        try:
            logger.info(
                "[Memory Idle Job] extract conv=%s… user=%s… idle since %s",
                conv_id[:8], str(user_id)[:8], c.get("updated_at"),
            )
            await extract_user_memory_background(
                user_id,
                conv_id,
                model_id or "unknown",
                provider_id or "unknown",
            )
            processed += 1
        except Exception as e:
            logger.error("[Memory Idle Job] extract failed for %s:", conv_id, exc_info=e)
            try:
                await mark_conversation_memory_extracted(conv_id)
            except Exception:
                pass
    if processed:
        logger.info("[Memory Idle Job] processed %s conversation(s)", processed)
    return processed


def _facts_to_summary_md(facts: list[dict], title: str | None = None) -> str:
    """Deterministic rolling summary from structured facts (no extra LLM call)."""
    if not facts:
        return ""

    identity: list[str] = []
    family: list[str] = []
    personal: list[str] = []
    by_cat: dict[str, list[str]] = {}

    for f in facts:
        cat = f.get("category") or "preference"
        key = (f.get("fact_key") or "").lower()
        text = (f.get("fact") or "").strip()
        if not text:
            continue

        if cat == "identity" and not _is_family_key(key) and not _looks_like_child_or_school_attr(text):
            identity.append(text)
        elif _is_family_key(key) or _RE_FAMILY_WORD.search(text) or (
            cat in ("identity", "personal") and _looks_like_child_or_school_attr(text)
        ):
            # Never put family attributes under "Identidade"; upgrade generic parentesco
            family.append(_enrich_family_fact(key if _is_family_key(key) else None, text))
        elif cat == "personal":
            personal.append(text)
        else:
            by_cat.setdefault(cat, []).append(text)

    labels = {
        "identity": "Identidade (titular da conta — NÃO confundir com família)",
        "family": "Família e outras pessoas (NÃO é o usuário)",
        "personal": "Pessoal",
        "professional": "Profissional",
        "project": "Projetos",
        "tech": "Tech",
        "preference": "Preferências",
    }
    lines: list[str] = []
    if title:
        lines.append(f"### {title}")

    def _emit(section_key: str, items: list[str], limit: int = 16) -> None:
        if not items:
            return
        lines.append(f"**{labels.get(section_key, section_key)}:**")
        for item in items[:limit]:
            # Keep multi-detail facts readable in the summary
            clipped = item if len(item) <= 220 else item[:217].rstrip() + "…"
            lines.append(f"- {clipped}")

    _emit("identity", identity, limit=10)
    _emit("family", family, limit=8)
    _emit("personal", personal, limit=8)
    _emit("professional", by_cat.get("professional") or [], limit=12)
    _emit("project", by_cat.get("project") or [], limit=14)
    for cat in ("tech", "preference"):
        _emit(cat, by_cat.get(cat) or [], limit=10)
    md = "\n".join(lines).strip()
    if len(md) > MEMORY_SUMMARY_MAX_CHARS:
        md = md[: MEMORY_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return md


async def _llm_refine_summary(
    user_id: str,
    base_md: str,
    provider_id: str | None,
    model_id: str | None,
    title: str,
) -> str | None:
    """
    Optional LLM polish of a deterministic summary.
    Controlled by meta.memory_llm_summaries_enabled (default: on if extractor model available).
    Falls back to None on any failure.
    """
    if not base_md.strip():
        return None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            enabled = await _get_meta(db, "memory_llm_summaries_enabled")
            # default enabled (None → True); explicit 0/false disables
            if enabled is not None and enabled in ("0", "false", "False", "no", "off"):
                return None
            provider, model_name, _src = await _get_extractor_provider_and_model(
                db,
                provider_id or "ollama",
                model_id or "unused",
                user_id,
            )
    except Exception:
        return None

    prompt = (
        "Reescreva o resumo abaixo em português, em markdown com bullets. "
        "Máximo ~35 linhas. Mantenha fatos estáveis e densos; SEM inventar; "
        "SEM raciocínio em aberto; SEM tags <think>.\n\n"
        "Seções nesta ordem (pule as vazias):\n"
        "1. **Identidade (usuário)** — só o titular\n"
        "2. **Família** — outras pessoas, com parentesco específico\n"
        "3. **Carreira** — empresas, papéis, stack\n"
        "4. **Projetos** — um bullet por projeto relevante (nome + o que é)\n"
        "5. **Preferências** — tom, idioma, estilo de trabalho\n\n"
        "REGRAS:\n"
        "- Idade/escola de filhos NUNCA em Identidade.\n"
        "- PARENTESCO: Esposa/Filho — nunca só \"(familiar)\".\n"
        "- Agrupe atributos da mesma pessoa num único bullet "
        "(ex.: Filho Nicolas Héron: ~9 anos, Escola Zulma).\n"
        "- Não quebre tabelas markdown em linhas soltas; resuma o essencial.\n"
        "- Não repita o prompt nem explique o que vai fazer.\n\n"
        f"Título: {title}\n\n{base_md}"
    )
    try:
        out = ""
        async for token in provider.stream_chat(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você resume memórias de usuário em markdown limpo. "
                        "Nunca confunda o usuário com familiares. "
                        "Preserve parentesco (Esposa/Filho). "
                        "Responda APENAS o markdown final — sem thinking, sem preâmbulo."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        ):
            out += str(token)
        out = _strip_llm_artifacts(out)
        if not out or _is_bad_summary_md(out):
            return None
        if len(out) > MEMORY_SUMMARY_MAX_CHARS:
            out = out[: MEMORY_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
        return out
    except Exception as e:
        logger.info("[Memory Summaries LLM] %s", e)
        return None


def _strip_llm_artifacts(text: str) -> str:
    """Remove chain-of-thought leaks and code fences from summary LLM output."""
    out = (text or "").strip()
    if not out:
        return ""
    out = re.sub(r"<think>[\s\S]*?</think>", "", out, flags=re.I)
    out = re.sub(r"<thinking>[\s\S]*?</thinking>", "", out, flags=re.I)
    out = re.sub(r"</?think>", "", out, flags=re.I)
    if out.startswith("```"):
        lines = out.splitlines()
        if len(lines) >= 3:
            out = "\n".join(lines[1:-1]).strip()
        else:
            out = out.strip("`").strip()
    cot_starts = (
        "okay, let's",
        "ok, let's",
        "let me ",
        "first, check",
        "first, i ",
        "i need to",
        "the user wants",
        "looking at the",
    )
    lines = out.splitlines()
    while lines and (
        lines[0].strip().lower().startswith(cot_starts)
        or lines[0].strip().lower().startswith("wait,")
        or (
            lines[0].strip()
            and not lines[0].strip().startswith(("#", "*", "-", "**"))
            and re.match(r"^(okay|ok|hmm|so |well |now |here )", lines[0].strip(), re.I)
            and len(lines) > 3
        )
    ):
        lines.pop(0)
    return "\n".join(lines).strip()


def _is_bad_summary_md(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t) < 30:
        return True
    if "<think" in t or "</think" in t:
        return True
    if t.count("filho(a)") >= 3 and "esposa" not in t and "filho " not in t:
        return True
    bad_phrases = (
        "let's tackle",
        "i need to rewrite",
        "the original summary",
        "máx. 14 linhas",
        "regras obrigatórias",
    )
    return any(p in t for p in bad_phrases)


async def refresh_memory_summaries(
    user_id: str,
    conversation_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    use_llm: bool = True,
) -> None:
    """
    Rebuild global summary from all active facts.
    If the conversation has a project_tag (or project.* fact keys exist),
    rebuild those project summaries too.
    Optionally refines with a cheap LLM (falls back to deterministic bullets).
    """
    # Corrige confusão identidade×família antes de regenerar o resumo
    try:
        await repair_identity_family_confusion(user_id)
    except Exception as e:
        logger.info("[Memory Summaries] repair: %s", e)

    facts = await get_user_memory(user_id, limit=200, active_only=True)

    # Sem fatos ativos → zera resumos (não deixar “fantasma” após Esquecer tudo)
    if not facts:
        try:
            await clear_all_memory_summaries(user_id)
        except Exception as e:
            logger.info("[Memory Summaries] clear empty: %s", e)
        return

    global_md = _facts_to_summary_md(facts, title="Resumo do usuário")
    if global_md:
        refined = None
        if use_llm:
            refined = await _llm_refine_summary(
                user_id, global_md, provider_id, model_id, "Resumo do usuário"
            )
        await upsert_memory_summary(
            user_id, "global", refined or global_md, scope_ref=""
        )
    else:
        try:
            await delete_memory_summary(user_id, "global", "")
        except Exception:
            pass

    project_names: set[str] = set()
    if conversation_id:
        project_tag = await get_conversation_project_tag(conversation_id)
        if project_tag:
            project_names.add(project_tag.strip().lower())

    for f in facts:
        key = (f.get("fact_key") or "").lower()
        if key.startswith("project.") and len(key) > 8:
            slug = key.split(".", 1)[1].replace("_", "-").strip()
            if slug:
                project_names.add(slug)

    for name_l in project_names:
        proj_facts = [
            f for f in facts
            if name_l in ((f.get("fact_key") or "") + " " + (f.get("fact") or "")).lower()
        ]
        if not proj_facts:
            proj_facts = [f for f in facts if f.get("category") == "project"][:8]
        md = _facts_to_summary_md(proj_facts, title=f"Projeto: {name_l}")
        if md:
            refined = None
            if use_llm:
                refined = await _llm_refine_summary(
                    user_id, md, provider_id, model_id, f"Projeto: {name_l}"
                )
            await upsert_memory_summary(
                user_id, "project", refined or md, scope_ref=name_l
            )

    # Remove resumos de projeto que não têm mais fatos associados
    try:
        await delete_orphaned_memory_summaries(user_id, project_names)
    except Exception as e:
        logger.info("[Memory Summaries] orphan cleanup: %s", e)


def build_memory_fingerprint(
    facts: list[dict],
    profile: dict | None = None,
    summaries: list[dict] | None = None,
) -> str:
    """
    Stable short hash of active memory + profile + summaries used as semantic-cache namespace.
    """
    parts: list[str] = []
    if profile:
        parts.append(
            f"p:{profile.get('display_name','')}|{profile.get('full_name','')}|"
            f"{profile.get('occupation','')}|{profile.get('custom_instructions','')}|"
            f"{profile.get('memory_enabled', 1)}"
        )
    for f in sorted(facts, key=lambda x: (x.get("id") or "")):
        parts.append(
            f"{f.get('id','')}:{f.get('updated_at','')}:{f.get('fact','')}:{f.get('is_active', 1)}"
        )
    for s in sorted(summaries or [], key=lambda x: (x.get("scope") or "", x.get("scope_ref") or "")):
        parts.append(
            f"s:{s.get('scope')}:{s.get('scope_ref')}:{s.get('updated_at')}:{s.get('summary_md','')[:80]}"
        )
    if not parts:
        return ""
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def build_profile_block(profile: dict | None) -> str:
    """Manual profile fields (server-side) injected into system prompt."""
    if not profile:
        return ""
    if not profile.get("memory_enabled", 1):
        return ""

    lines: list[str] = []
    display = (profile.get("display_name") or "").strip()
    full = (profile.get("full_name") or "").strip()
    occupation = (profile.get("occupation") or "").strip()
    instructions = (profile.get("custom_instructions") or "").strip()

    if display:
        lines.append(f"- Nome preferido: {display}")
    if full and full != display:
        lines.append(f"- Nome completo: {full}")
    if occupation:
        lines.append(f"- Área / trabalho: {occupation}")
    if instructions:
        lines.append(f"- Instruções personalizadas: {instructions}")

    if not lines:
        return ""

    return (
        "\n[PERFIL DO USUÁRIO]\n"
        + "\n".join(lines)
        + "\n"
    )


def build_summary_block(
    global_summary: dict | None = None,
    project_summary: dict | None = None,
) -> str:
    """Inject rolling summaries (global + optional active project)."""
    chunks: list[str] = []
    if global_summary and (global_summary.get("summary_md") or "").strip():
        chunks.append(
            "\n[RESUMO GLOBAL DO USUÁRIO]\n"
            "Atenção: seções de Família referem-se a OUTRAS pessoas; "
            "nunca use idade/escola de familiares como se fossem do usuário.\n"
            + global_summary["summary_md"].strip()
            + "\n"
        )
    if project_summary and (project_summary.get("summary_md") or "").strip():
        ref = project_summary.get("scope_ref") or "projeto"
        chunks.append(
            f"\n[RESUMO DO PROJETO ATIVO: {ref}]\n"
            + project_summary["summary_md"].strip()
            + "\n"
        )
    return "".join(chunks)


def build_memory_block(
    facts: list[dict],
    profile: dict | None = None,
    global_summary: dict | None = None,
    project_summary: dict | None = None,
) -> str:
    """
    Builds the markdown block injected into the system prompt.
    Order: profile → summaries → fact bullets (with hard char cap).
    """
    profile_part = build_profile_block(profile)

    if profile and not profile.get("memory_enabled", 1):
        return profile_part

    summary_part = build_summary_block(global_summary, project_summary)

    if not facts and not profile_part and not summary_part:
        return ""

    lines = []
    total_chars = len(profile_part) + len(summary_part)

    identity_lines: list[str] = []
    family_lines: list[str] = []
    by_cat: dict[str, list[str]] = {}

    for f in facts or []:
        cat = f.get("category", "preference")
        key = (f.get("fact_key") or "").lower()
        fact_text = (f.get("fact") or "").strip()
        if not fact_text:
            continue
        if cat == "identity" and not _is_family_key(key) and not _looks_like_child_or_school_attr(fact_text):
            identity_lines.append(fact_text)
        elif _is_family_key(key) or _RE_FAMILY_WORD.search(fact_text) or (
            cat in ("identity", "personal") and _looks_like_child_or_school_attr(fact_text)
        ):
            family_lines.append(
                _enrich_family_fact(key if _is_family_key(key) else None, fact_text)
            )
        else:
            by_cat.setdefault(cat, []).append(fact_text)

    category_order = [
        ("identity", "Identidade do usuário (titular)"),
        ("family", "Família e outras pessoas (NÃO é o usuário)"),
        ("personal", "Pessoal"),
        ("professional", "Profissional"),
        ("project", "Projetos Ativos"),
        ("tech", "Tecnologias"),
        ("preference", "Preferências"),
    ]

    section_items = {
        "identity": identity_lines,
        "family": family_lines,
        "personal": by_cat.get("personal") or [],
        "professional": by_cat.get("professional") or [],
        "project": by_cat.get("project") or [],
        "tech": by_cat.get("tech") or [],
        "preference": by_cat.get("preference") or [],
    }

    for cat_key, label in category_order:
        items = section_items.get(cat_key) or []
        if not items:
            continue
        header = f"\n**{label}:**"
        lines.append(header)
        for fact_text in items:
            line = f"- {fact_text}"
            if total_chars + len(line) > MEMORY_INJECT_MAX_CHARS:
                break
            lines.append(line)
            total_chars += len(line)

    facts_part = ""
    if any(l.startswith("-") for l in lines):
        facts_part = (
            "\n[CONTEXTO SOBRE O USUÁRIO — use quando relevante; não cite este bloco textualmente]\n"
            "REGRAS: (1) Identidade = só o titular da conta. "
            "(2) Família = outras pessoas; NUNCA diga que a idade/escola de um filho é do usuário. "
            "(3) Se perguntarem a idade do usuário e só houver idade de familiar, diga que não sabe "
            "a idade do usuário (ou peça confirmação), sem inventar.\n"
            + "\n".join(lines)
            + "\n"
        )

    return profile_part + summary_part + facts_part


# --- Importar memória de outros provedores (Claude dated + markdown rico) ----

EXTERNAL_MEMORY_EXPORT_PROMPT = (
    "Export all of my stored memories and any context you've learned about me "
    "from past conversations. Preserve my words verbatim where possible, "
    "especially for instructions and preferences.\n\n"
    "## Categories (output in this order):\n\n"
    "1. **Instructions**: Rules I've explicitly asked you to follow going forward "
    "— tone, format, style, \"always do X\", \"never do Y\", and corrections to your "
    "behavior. Only include rules from stored memories, not from conversations.\n\n"
    "2. **Identity**: Name, age, location, education, family, relationships, "
    "languages, and personal interests.\n\n"
    "3. **Career**: Current and past roles, companies, and general skill areas.\n\n"
    "4. **Projects**: Projects I meaningfully built or committed to. Ideally ONE "
    "entry per project. Include what it does, current status, and any key decisions. "
    "Use the project name or a short descriptor as the first words of the entry.\n\n"
    "5. **Preferences**: Opinions, tastes, and working-style preferences that apply broadly.\n\n"
    "## Format:\n\n"
    "Use section headers for each category. Within each category, list one entry "
    "per line, sorted by oldest date first. Format each line as:\n\n"
    "[YYYY-MM-DD] - Entry content here.\n\n"
    "If no date is known, use [unknown] instead.\n\n"
    "Alternatively, a structured personal/professional profile in Markdown "
    "(## Identity, ## Career, ## Projects, ## Preferences) is also accepted.\n\n"
    "## Output:\n"
    "- Wrap the entire export in a single code block for easy copying.\n"
    "- After the code block, state whether this is the complete set or if more remain."
)

# Logical section → (memory category, fact_key prefix)
_IMPORT_SECTION_META = {
    "instructions": ("preference", "prefs.rule"),
    "identity": ("identity", "identity.import"),
    "family": ("personal", "family.import"),
    "career": ("professional", "work.import"),
    "projects": ("project", "project.import"),
    "preferences": ("preference", "prefs.import"),
    "health": ("personal", "personal.health"),
    "updates": ("personal", "personal.update"),
    "tech": ("tech", "tech.import"),
}

_RE_CODE_FENCE = re.compile(r"```(?:\w+)?\s*\n([\s\S]*?)```", re.M)
_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_RE_MD_BULLET = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
_RE_MD_KV = re.compile(
    r"^\s*(?:\*\*|__)?"
    r"\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 /&+.\-]{0,48}?)"
    r"\s*(?:\*\*|__)?"
    r"\s*:\s*"
    r"(.+?)\s*$"
)
_RE_DATED_EXPORT = re.compile(
    r"^\s*(?:[-*•]\s*)?\[?\s*(?P<date>\d{4}-\d{2}-\d{2}|unknown|desconhecido|n/?a)\s*\]?"
    r"\s*[-–—:]\s*(?P<body>.+)$",
    re.I,
)
_RE_TABLE_SEP = re.compile(r"^\s*\|?[\s\-:|]+\|?\s*$")


def _strip_import_wrappers(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    blocks = _RE_CODE_FENCE.findall(text)
    if blocks:
        text = max(blocks, key=len).strip()
    return text


def _slug_hash(text: str, n: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def _clean_md_inline(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^>\s*", "", t)
    # Leftover bold markers from odd **Key:** patterns
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"\s+", " ", t).strip(" \t-–—|*")
    return t


def _parse_kv_line(stripped: str) -> tuple[str, str] | None:
    """Parse '**Key:** value' / 'Key: value' without swallowing markdown markers into the value."""
    s = (stripped or "").strip()
    if ":" not in s:
        return None
    # Strip wrapping bold around the whole key side
    s_norm = re.sub(r"^\*\*(.+?)\*\*\s*:", r"\1:", s)
    s_norm = re.sub(r"^__(.+?)__\s*:", r"\1:", s_norm)
    # Also **Key:**value (colon inside bold)
    s_norm = re.sub(r"^\*\*([^*:]+):\*\*\s*", r"\1: ", s_norm)
    if ":" not in s_norm:
        return None
    key, val = s_norm.split(":", 1)
    key = _clean_md_inline(key)
    val = _clean_md_inline(val)
    if not key or not val or len(key) > 48:
        return None
    # Avoid treating URLs / times as KV
    if key.lower().startswith("http") or re.match(r"^\d+$", key):
        return None
    return key, val


def _is_noise_import_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if re.match(r"^[-*_=~]{3,}$", s):
        return True
    if _RE_TABLE_SEP.match(s):
        return True
    if re.match(r"^\|[-:\s|]+\|$", s):
        return True
    # broken table fragments without content
    if s.count("|") >= 2:
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(not c or re.match(r"^[-:]+$", c) for c in cells):
            return True
    # pure punctuation / emoji-ish
    alnum = re.sub(r"[\W_]+", "", s, flags=re.UNICODE)
    if len(alnum) < 2:
        return True
    return False


def _heading_to_section(title: str) -> str | None:
    """Map a markdown heading to a logical import section."""
    t = _clean_md_inline(title).lower()
    t = re.sub(r"^\d+[\.\)]\s*", "", t)
    # strip leading emoji / symbols
    t = re.sub(r"^[^\wÀ-ÿ]+", "", t, flags=re.UNICODE).strip()

    # Order matters: more specific before broad (e.g. preferências before "trabalho")
    rules: list[tuple[str, tuple[str, ...]]] = [
        ("instructions", ("instruction", "instruç", "instruc", "regras", "other instructions")),
        ("family", ("família", "familia", "family", "relationships")),
        (
            "preferences",
            (
                "preferên",
                "preferen",
                "estilo de trabalho",
                "working-style",
                "comunicação",
                "comunicacao",
                "abordagem técnica",
                "abordagem tecnica",
                "especializa",
                "top of mind",
            ),
        ),
        (
            "identity",
            (
                "identidade",
                "identity",
                "perfil pessoal",
                "dados pessoais",
                "personal context",
                "sobre mim",
            ),
        ),
        (
            "projects",
            (
                "projeto",
                "project",
                "em andamento",
                "agentes e",
                "automação ia",
                "automacao ia",
                "negócio",
                "negocio",
                "empreendedor",
                "comunitár",
                "comunitar",
                "ideias conceitu",
                "conceituais",
            ),
        ),
        (
            "career",
            (
                "carreira",
                "career",
                "profissional",
                "empresas e",
                "empresas",
                "atuação",
                "atuacao",
                "work context",
                "outros papéis",
                "outros papeis",
                "ocupação",
                "ocupacao",
            ),
        ),
        (
            "health",
            ("saúde e", "saude e", "saúde", "saude", "lifestyle", "nutrição", "nutricao", "protocolo de pept"),
        ),
        ("updates", ("atualiza", "update recent", "brief history", "long-term background")),
        ("tech", ("tecnologia", "hardware", "stack tech")),
    ]
    for section, keys in rules:
        if any(k in t for k in keys):
            return section
    # Soft fallbacks
    if re.search(r"\b(trabalho|work)\b", t) and "prefer" not in t:
        return "career"
    if re.search(r"\b(comunica|t[oó]pico)", t):
        return "preferences"
    return None


def _clip_fact(text: str, max_chars: int = MEMORY_IMPORT_FACT_MAX_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _make_import_fact(
    section: str,
    body: str,
    *,
    entity: str | None = None,
    date: str | None = None,
) -> dict | None:
    body = _clean_md_inline(body)
    if not body or len(body) < 3:
        return None
    if _is_noise_import_line(body):
        return None

    # Skip pure label-like leftovers
    if body.lower() in ("categoria", "foco", "nome", "função", "funcao"):
        return None

    cat, key_prefix = _IMPORT_SECTION_META.get(section, ("preference", "import.misc"))

    if entity:
        entity_c = _clean_md_inline(entity)
        if entity_c and not body.lower().startswith(entity_c.lower()[:20]):
            body = f"{entity_c}: {body}"

    if date and date.lower() not in ("unknown", "desconhecido", "n/a", "na"):
        body = f"[{date}] {body}"

    body = _clip_fact(body)
    fact_key_cat = cat
    fact_key = f"{key_prefix}.{_slug_hash(body.lower())}"

    # Family / kinship routing
    is_familyish = (
        section == "family"
        or _RE_FAMILY_WORD.search(body)
        or re.search(r"\b(esposa|esposo|filho|filha|wife|husband|son|daughter|c[oô]njuge)\b", body, re.I)
    )
    if is_familyish and section in ("identity", "family", "health", "updates", "preferences"):
        fact_key_cat = "personal"
        if re.search(r"\b(esposa|esposo|c[oô]njuge|wife|husband|spouse)\b", body, re.I):
            fact_key = f"family.spouse_import.{_slug_hash(body.lower())}"
            # "Vera Lúcia (esposa, ~42)" → "Esposa Vera Lúcia: ~42…"
            m = re.match(
                r"^(.+?)\s*\(\s*(esposa|esposo|wife|husband|c[oô]njuge)\b([^)]*)\)\s*[-–—:]?\s*(.*)$",
                body,
                re.I,
            )
            if m:
                name, role, extra, rest = m.group(1).strip(), m.group(2).lower(), m.group(3).strip(" ,"), m.group(4).strip()
                role_pt = "Esposa" if role in ("esposa", "wife") else ("Esposo" if role in ("esposo", "husband") else "Cônjuge")
                detail = ", ".join(x for x in (extra, rest) if x)
                body = f"{role_pt} {name}" + (f": {detail}" if detail else "")
        elif re.search(r"\b(filho|filha|son|daughter)\b", body, re.I):
            fact_key = f"family.child_import.{_slug_hash(body.lower())}"
            m = re.match(
                r"^(.+?)\s*\(\s*(filho|filha|son|daughter)\b([^)]*)\)\s*[-–—:]?\s*(.*)$",
                body,
                re.I,
            )
            if m:
                name, role, extra, rest = m.group(1).strip(), m.group(2).lower(), m.group(3).strip(" ,"), m.group(4).strip()
                role_pt = "Filha" if role in ("filha", "daughter") else "Filho"
                detail = ", ".join(x for x in (extra, rest) if x)
                body = f"{role_pt} {name}" + (f": {detail}" if detail else "")
        else:
            fact_key = f"family.import.{_slug_hash(body.lower())}"
        body = _enrich_family_fact(fact_key, body)
    elif section == "identity":
        # Named identity fields
        low = body.lower()
        if re.match(r"^(nome|name)\b", low):
            fact_key = "identity.full_name"
            # Normalize "Nome: X" → keep full line
        elif re.search(r"\b(localiza|location|cidade|bairro|endere[cç]o|blumenau)\b", low):
            fact_key = f"identity.location.{_slug_hash(body.lower())}"
        elif re.search(r"\b(religi|testemunha|jeov)\b", low):
            fact_key = f"identity.belief.{_slug_hash(body.lower())}"
        else:
            fact_key = f"identity.import.{_slug_hash(body.lower())}"
        fact_key_cat = "identity"
    elif section == "instructions":
        fact_key_cat = "preference"
        fact_key = f"prefs.rule.{_slug_hash(body.lower())}"
    elif section == "projects" or fact_key_cat == "project":
        fact_key_cat = "project"
        slug_src = entity or body
        slug = re.sub(r"[^a-z0-9]+", "_", slug_src[:48].lower()).strip("_")
        fact_key = f"project.{slug[:40]}" if slug else f"project.import.{_slug_hash(body.lower())}"
    elif section == "career":
        fact_key_cat = "professional"
        slug_src = entity or body
        slug = re.sub(r"[^a-z0-9]+", "_", slug_src[:40].lower()).strip("_")
        fact_key = f"work.{slug[:36]}" if slug else f"work.import.{_slug_hash(body.lower())}"

    # Drop ultra-short fragments that are not identity names
    if len(body) < 6 and fact_key_cat != "identity":
        return None

    return {
        "category": fact_key_cat if fact_key_cat in MEMORY_CATEGORIES else "preference",
        "fact": body,
        "fact_key": fact_key,
        "confidence": 0.9,
    }


def _looks_like_dated_export(text: str) -> bool:
    """True when most content lines look like Claude [date] - entry format."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 3:
        return False
    dated = sum(1 for ln in lines if _RE_DATED_EXPORT.match(ln))
    return dated >= max(3, int(len(lines) * 0.35))


def _parse_dated_export(text: str) -> tuple[list[dict], list[str], list[str]]:
    """Legacy Claude-style [YYYY-MM-DD] - line parser."""
    current: str | None = None
    sections: list[str] = []
    facts: list[dict] = []
    instructions: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        hm = _RE_MD_HEADING.match(line)
        if hm:
            sec = _heading_to_section(hm.group(2))
            if sec:
                current = sec
                if sec not in sections:
                    sections.append(sec)
            continue
        # bare section labels
        sec2 = _heading_to_section(line.rstrip(":"))
        if sec2 and len(line) < 40 and not _RE_DATED_EXPORT.match(line):
            current = sec2
            if sec2 not in sections:
                sections.append(sec2)
            continue
        if not current:
            continue
        m = _RE_DATED_EXPORT.match(line)
        if m:
            date = (m.group("date") or "").strip()
            body = m.group("body").strip()
            if date.lower() in ("unknown", "desconhecido", "n/a", "na"):
                date = None
            fact = _make_import_fact(current, body, date=date)
            if fact:
                facts.append(fact)
                if current == "instructions":
                    instructions.append(_clean_md_inline(body))
            continue
        bm = _RE_MD_BULLET.match(line)
        if bm:
            fact = _make_import_fact(current, bm.group(1))
            if fact:
                facts.append(fact)
                if current == "instructions":
                    instructions.append(_clean_md_inline(bm.group(1)))
    return facts, sections, instructions


def _parse_rich_markdown_profile(text: str) -> tuple[list[dict], list[str], list[str], dict]:
    """
    Parse free-form personal/professional markdown profiles
    (## sections, ###/#### entities, bullets, Key: value).
    """
    current_section: str | None = None
    entity: str | None = None
    entity_bits: list[str] = []
    sections: list[str] = []
    facts: list[dict] = []
    instructions: list[str] = []
    profile: dict = {}

    def _is_container_heading(title: str) -> bool:
        t = title.lower()
        return bool(
            re.search(
                r"^(empresas|atua[cç][aã]o|outros pap[eé]is|neg[oó]cios|empreendedor|"
                r"agentes e|automa[cç][aã]o|projetos comunit|ideias|conceitu|"
                r"comunica[cç][aã]o|abordagem|especializa|t[oó]picos)",
                t,
            )
        )

    def flush_entity() -> None:
        nonlocal entity, entity_bits
        if entity and entity_bits and current_section:
            joined = "; ".join(entity_bits[:12])
            fact = _make_import_fact(current_section, joined, entity=entity)
            if fact:
                facts.append(fact)
        elif (
            entity
            and current_section in ("projects", "career")
            and not _is_container_heading(entity)
            and len(entity) >= 4
        ):
            # Named project/company without bullets still counts
            fact = _make_import_fact(current_section, entity, entity=entity)
            if fact:
                facts.append(fact)
        entity = None
        entity_bits = []

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if _is_noise_import_line(stripped):
            continue

        hm = _RE_MD_HEADING.match(stripped)
        if hm:
            level = len(hm.group(1))
            title = _clean_md_inline(hm.group(2))
            sec = _heading_to_section(title)

            if level <= 2:
                flush_entity()
                if sec:
                    current_section = sec
                    if sec not in sections:
                        sections.append(sec)
                elif re.search(r"perfil|pessoal e profissional|about me", title, re.I):
                    current_section = "identity"
                    if "identity" not in sections:
                        sections.append("identity")
                    # "Perfil … - Osmar Gonçalves"
                    mname = re.search(
                        r"[-–—]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ]+){1,4})\s*$",
                        title,
                    )
                    if mname:
                        profile["full_name"] = mname.group(1).strip()
                        profile.setdefault("display_name", mname.group(1).split()[0])
                entity = None
                continue

            # ### / #### — NEVER reclassify section from entity titles
            # (avoids "Peptide E-commerce" → health). Only explicit family / prefs topics.
            flush_entity()
            if current_section is None:
                current_section = sec or "identity"
                if current_section not in sections:
                    sections.append(current_section)

            if sec == "family":
                current_section = "family"
                if "family" not in sections:
                    sections.append("family")
                entity = None
            elif sec in ("preferences", "instructions"):
                # ### Comunicação / Abordagem under Preferências
                current_section = sec
                if sec not in sections:
                    sections.append(sec)
                entity = None if _is_container_heading(title) else None
            elif _is_container_heading(title):
                entity = None
            elif current_section in ("career", "projects", "preferences", "health", "tech"):
                entity = title
            else:
                entity = None
            continue
        # Bold-only subheads like **Família:**
        bold_head = re.match(r"^\*\*([^*]+)\*\*\s*:?\s*$", stripped)
        if bold_head:
            ht = bold_head.group(1).strip()
            sec = _heading_to_section(ht)
            if sec == "family":
                flush_entity()
                current_section = "family"
                if "family" not in sections:
                    sections.append("family")
            elif sec and current_section in (None, "preferences", "identity"):
                flush_entity()
                current_section = sec
                if sec not in sections:
                    sections.append(sec)
            continue

        if current_section is None:
            # Title line with name
            if re.search(r"osmar|perfil|professional", stripped, re.I) and len(stripped) < 120:
                current_section = "identity"
                if "identity" not in sections:
                    sections.append("identity")
            else:
                continue

        # Key: value (Nome:, Localização:, Função:)
        parsed_kv = _parse_kv_line(stripped)
        if parsed_kv:
            key, val = parsed_kv
            combo = f"{key}: {val}"
            key_l = key.lower()

            if re.search(r"^(nome|name|full.?name|nome completo)$", key_l):
                profile["full_name"] = val
                profile.setdefault("display_name", val.split()[0] if val else None)
                facts.append(
                    {
                        "category": "identity",
                        "fact": f"Nome completo: {val}",
                        "fact_key": "identity.full_name",
                        "confidence": 0.95,
                    }
                )
                continue
            if re.search(r"localiza|cidade|endere|bairro", key_l):
                profile.setdefault("location", val)
                facts.append(
                    {
                        "category": "identity",
                        "fact": f"Localização: {val}",
                        "fact_key": f"identity.location.{_slug_hash(val.lower())}",
                        "confidence": 0.92,
                    }
                )
                continue
            if re.search(r"dados pessoais", key_l):
                facts.append(
                    {
                        "category": "identity",
                        "fact": f"Dados pessoais: {val}",
                        "fact_key": f"identity.bio.{_slug_hash(val.lower())}",
                        "confidence": 0.9,
                    }
                )
                continue
            if re.search(
                r"fun[cç][aã]o|role|cargo|co-?fundador|atua[cç][aã]o|hor[aá]rio|presen[cç]a",
                key_l,
            ) and entity:
                entity_bits.append(combo)
                continue

            target = current_section or "identity"
            if re.search(r"esposa|filho|filha|fam[ií]lia|pai|m[aã]e", key_l + " " + val, re.I):
                target = "family"
            if entity and current_section in ("career", "projects"):
                entity_bits.append(combo)
            else:
                fact = _make_import_fact(target, combo, entity=entity if not entity_bits else None)
                if fact:
                    facts.append(fact)
                    if target == "instructions":
                        instructions.append(val)
            continue

        # Bullets
        bm = _RE_MD_BULLET.match(stripped)
        if bm:
            body = _clean_md_inline(bm.group(1))
            if not body:
                continue
            # Nested family under identity when line mentions wife/son
            target = current_section
            if current_section == "identity" and (
                _RE_FAMILY_WORD.search(body)
                or re.search(r"\b(esposa|filho|filha|wife|son)\b", body, re.I)
            ):
                target = "family"
            if entity and current_section in ("career", "projects", "health", "preferences"):
                entity_bits.append(body)
            else:
                fact = _make_import_fact(target, body)
                if fact:
                    facts.append(fact)
                    if target == "instructions" or current_section == "preferences" and re.search(
                        r"\b(sempre|nunca|always|never|responda|idioma|tom)\b", body, re.I
                    ):
                        instructions.append(body)
            continue

        # Dated line inside rich doc
        dm = _RE_DATED_EXPORT.match(stripped)
        if dm:
            date = dm.group("date")
            if date.lower() in ("unknown", "desconhecido", "n/a"):
                date = None
            fact = _make_import_fact(current_section, dm.group("body"), entity=entity, date=date)
            if fact:
                facts.append(fact)
            continue

        # Plain prose under a section (address lines, taglines)
        plain = _clean_md_inline(stripped)
        if plain and len(plain) >= 12 and not plain.startswith("|"):
            # Address / CEP lines under identity
            if current_section == "identity" and re.search(
                r"\b(rua|av\.|cep|bairro|sc\b|apartamento|ap\.)\b", plain, re.I
            ):
                fact = _make_import_fact("identity", f"Endereço: {plain}")
                if fact:
                    facts.append(fact)
            elif current_section in ("preferences", "instructions") and len(plain) >= 20:
                fact = _make_import_fact(current_section, plain)
                if fact:
                    facts.append(fact)
                    if current_section == "instructions":
                        instructions.append(plain)
            elif entity and current_section in ("career", "projects"):
                entity_bits.append(plain)

    flush_entity()
    return facts, sections, instructions, profile


def _dedupe_facts(facts: list[dict]) -> list[dict]:
    seen_keys: set[str] = set()
    seen_text: set[str] = set()
    out: list[dict] = []
    for f in facts:
        key = (f.get("fact_key") or "").lower()
        text = re.sub(r"\s+", " ", (f.get("fact") or "").strip().lower())
        if key and key in seen_keys:
            continue
        if text in seen_text:
            continue
        if key:
            seen_keys.add(key)
        seen_text.add(text)
        out.append(f)
    return out


def _prioritize_import_facts(facts: list[dict], limit: int = MEMORY_IMPORT_MAX_FACTS) -> list[dict]:
    order = {
        "identity": 0,
        "personal": 1,
        "professional": 2,
        "project": 3,
        "tech": 4,
        "preference": 5,
    }
    ranked = sorted(
        facts,
        key=lambda f: (
            order.get(f.get("category") or "", 9),
            0 if (f.get("fact_key") or "").startswith(("identity.", "family.spouse", "family.child", "work.", "project.")) else 1,
            -len(f.get("fact") or ""),
        ),
    )
    return ranked[:limit]


def parse_external_memory_export(raw_text: str) -> dict:
    """
    Parse external AI memory dumps into structured facts.

    Supports:
      - Claude-style dated exports ([YYYY-MM-DD] - entry)
      - Rich markdown profiles (## Identity / ## Career / #### Company …)

    Returns:
      facts, instructions_blob, sections_found, entry_count, profile_hints
    """
    text = _strip_import_wrappers(raw_text)
    if not text:
        return {
            "facts": [],
            "instructions_blob": None,
            "sections_found": [],
            "entry_count": 0,
            "profile_hints": {},
        }

    profile_hints: dict = {}
    if _looks_like_dated_export(text):
        facts, sections, instructions = _parse_dated_export(text)
    else:
        facts, sections, instructions, profile_hints = _parse_rich_markdown_profile(text)
        # If rich parse found almost nothing, try dated as fallback
        if len(facts) < 5:
            f2, s2, i2 = _parse_dated_export(text)
            if len(f2) > len(facts):
                facts, sections, instructions = f2, s2, i2

    facts = _dedupe_facts(facts)
    facts = _prioritize_import_facts(facts)

    instructions_blob = None
    if instructions:
        # de-dupe instruction lines
        uniq: list[str] = []
        seen: set[str] = set()
        for x in instructions:
            k = x.lower().strip()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(x)
        instructions_blob = "\n".join(f"- {x}" for x in uniq[:40])

    return {
        "facts": facts,
        "instructions_blob": instructions_blob,
        "sections_found": sections,
        "entry_count": len(facts),
        "profile_hints": profile_hints or {},
    }

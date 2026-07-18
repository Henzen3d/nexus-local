import httpx
import re
import asyncio
import logging

from backend.logging_config import get_logger
logger = get_logger(__name__)

logger = logging.getLogger(__name__)

async def fetch_freellm_models():
    """
    Tenta realizar o scraping da tabela de modelos de freellm.net.
    NOTA: O site possui proteção que frequentemente bloqueia scrapers simples (HTTP 403 Forbidden),
    especialmente quando hospedado atrás de Cloudflare. Este script funciona como um 
    mecanismo 'best-effort' (desacoplado do mnfst) para buscar campos como 'score' e 'weekly_tokens'.
    """
    url = "https://freellm.net/models/"
    # Fornecer um User-Agent para tentar mitigar bloqueios básicos
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"freellm_scraper: falhou ao conectar em freellm.net - {e}")
        return {"status": "error", "error": str(e), "models": []}

    html = resp.text
    
    # Extrai os modelos com regex (heurística para não quebrar com mudanças no React/Next.js)
    # Busca âncoras no formato href="/models/provider/model-id"
    pattern = re.compile(r'<a[^>]+href=["\']/models/([^/]+)/([^/\'"]+)/?["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    
    matches = pattern.findall(html)
    results = []
    
    for provider, model_raw, inner_html in matches:
        # A API e as páginas usam IDs normalizados. Aqui podemos tentar achar indícios de score
        # Se a interface colocar o score próximo ao modelo, um parser de BeautifulSoup seria ideal, 
        # mas como bs4 não é dependência padrão do pipeline e o layout é incerto, extraímos o básico.
        clean_name = re.sub(r'<[^>]+>', '', inner_html).strip()
        
        # Ignora links de navegação corrompidos
        if clean_name and not clean_name.startswith("http"):
            results.append({
                "provider": provider,
                "model_id_raw": model_raw,
                "display_name": clean_name,
                "score": None,          # Placeholder para futura expansão de regex mais complexo
                "weekly_tokens": None   # Placeholder para futura expansão
            })
            
    # Remove duplicatas que possam surgir de links no header/footer vs tabela principal
    unique_models = {}
    for r in results:
        key = f"{r['provider']}:{r['model_id_raw']}"
        if key not in unique_models:
            unique_models[key] = r
            
    models_list = list(unique_models.values())
    
    logger.info(f"freellm_scraper: Encontrados {len(models_list)} modelos no scrape.")
    
    return {
        "status": "success",
        "models_found": len(models_list),
        "models": models_list
    }

async def run_freellm_scraper_job(db):
    """
    Função para ser invocada de forma agendada ou manual,
    salvando/atualizando informações de score no banco de dados se disponíveis.
    """
    report = await fetch_freellm_models()
    if report["status"] == "error":
        return report
        
    models = report.get("models", [])
    # Aqui, a lógica de injeção atualizaria a tabela `models` ou `model_rankings`.
    # Como este é um scraper isolado (Fase 6.4 - Opcional), no momento apenas registramos o sucesso
    # para evitar sobrescrever a curadoria principal (mnfst) de maneira destrutiva.
    logger.info("freellm_scraper: Scraping concluído. Pronto para injeção de score/tokens.")
    
    return report

if __name__ == "__main__":
    # Teste local direto
    import logging

    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(fetch_freellm_models())
    logger.info("Status: %s, Encontrados: %s", result['status'], result.get('models_found'))
